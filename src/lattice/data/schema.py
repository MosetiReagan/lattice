"""Dataset records distinguish references, procedural checks and unscored code."""

import hashlib
import json
import unicodedata
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    kind: Literal[
        "number",
        "choice",
        "boolean",
        "span",
        "program",
        "constraints",
        "document",
        "json",
        "text",
        "list",
    ]
    value: Any = None
    alternatives: list[str] = Field(default_factory=list)
    checks: list[dict] = Field(default_factory=list)


class DataRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    schema_version: Literal[1] = 1
    id: str = Field(min_length=1, max_length=256)
    dataset: str = Field(min_length=1, max_length=128)
    family: str = Field(min_length=1, max_length=128)
    source_split: str
    partition: Literal["development", "validation", "evaluation", "corpus"]
    group_id: str
    prompt: str = Field(min_length=1, max_length=200000)
    reference: Reference
    scorer: str
    license: str
    source: dict
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def consistent(self):
        reference = self.reference
        if reference.kind == "choice":
            labels = self.metadata.get("choice_labels", [])
            if reference.value not in labels or len(labels) != len(set(labels)):
                raise ValueError(
                    "Choice gold must identify exactly one available label"
                )
        if reference.kind == "boolean" and type(reference.value) is not bool:
            raise ValueError("Boolean gold must be an actual boolean")
        if reference.kind in ("number", "text") and not isinstance(
            reference.value, str
        ):
            raise ValueError("Number/text gold must preserve a canonical string")
        if reference.kind == "span" and not all(
            isinstance(x, str) for x in reference.alternatives
        ):
            raise ValueError("Span answers must be strings")
        if reference.kind == "constraints" and not reference.checks:
            raise ValueError("Procedural tasks require explicit checks")
        if reference.kind == "program" and not self.metadata.get("execution_required"):
            raise ValueError(
                "Code tasks cannot claim execution correctness from parsing"
            )
        return self

    def prompt_sha256(self) -> str:
        return hashlib.sha256(self.prompt.encode()).hexdigest()

    def content_sha256(self) -> str:
        # Does not include labels/IDs or collapse numeric differences in real tasks.
        text = " ".join(unicodedata.normalize("NFC", self.prompt).split())
        return hashlib.sha256(text.encode()).hexdigest()

    def reference_sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.reference.model_dump(), sort_keys=True, ensure_ascii=False
            ).encode()
        ).hexdigest()
