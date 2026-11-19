"""Apply worker limits in a fresh interpreter, then exec without a shell.

Avoids preexec_fn: the parent may already have hash-check or HTTP threads.
"""

import os
import resource
import sys


def main() -> None:
    limit = int(sys.argv[1]) * 1024**2
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.execv(sys.argv[2], sys.argv[2:])


if __name__ == "__main__":
    main()
