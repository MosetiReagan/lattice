"""Read bounded GGUF metadata only to fingerprint exact tokenizer identity.

Does not load tensors, run model code or assume matching vocabulary size suffices.
"""

import hashlib
import struct
from pathlib import Path

_FORMAT = {
    0: "B",
    1: "b",
    2: "H",
    3: "h",
    4: "I",
    5: "i",
    6: "f",
    7: "?",
    10: "Q",
    11: "q",
    12: "d",
}


def tokenizer_fingerprint(path: Path) -> str:
    hashes = {}
    with path.open("rb") as source:
        budget = 64 * 1024**2

        def read(n):
            nonlocal budget
            if not 0 <= n <= budget:
                raise ValueError("GGUF metadata exceeds safe bound")
            data = source.read(n)
            if len(data) != n:
                raise ValueError("Truncated GGUF metadata")
            budget -= n
            return data

        def integer(fmt):
            return struct.unpack("<" + fmt, read(struct.calcsize(fmt)))[0]

        def string():
            return read(integer("Q"))

        def value(kind, digest):
            if kind in _FORMAT:
                digest.update(read(struct.calcsize(_FORMAT[kind])))
            elif kind == 8:
                data = string()
                digest.update(struct.pack("<Q", len(data)))
                digest.update(data)
            elif kind == 9:
                subtype, count = integer("I"), integer("Q")
                if subtype == 9 or count > 2_000_000:
                    raise ValueError("Unsupported or oversized GGUF array")
                digest.update(struct.pack("<IQ", subtype, count))
                for _ in range(count):
                    value(subtype, digest)
            else:
                raise ValueError("Unknown GGUF metadata type")

        if read(4) != b"GGUF" or integer("I") not in (2, 3):
            raise ValueError("Expected GGUF v2/v3")
        integer("Q")  # tensor count; tensor bytes are never parsed
        fields = integer("Q")
        if fields > 10000:
            raise ValueError("Oversized GGUF metadata count")
        for _ in range(fields):
            name = string().decode("utf-8")
            kind = integer("I")
            digest = hashlib.sha256(struct.pack("<I", kind))
            value(kind, digest)
            if name.startswith("tokenizer."):
                if name in hashes:
                    raise ValueError("Duplicate tokenizer field")
                hashes[name] = digest.hexdigest()
    if "tokenizer.ggml.tokens" not in hashes:
        raise ValueError("GGUF lacks tokenizer vocabulary")
    return hashlib.sha256(repr(sorted(hashes.items())).encode()).hexdigest()
