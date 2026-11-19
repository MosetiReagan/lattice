"""Validated public inputs and intentionally narrow baseline capabilities."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LatticeError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = "invalid_request"):
        super().__init__(message)
        self.status, self.code = status, code


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=32768)


class Optimization(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    # Adaptive/quantized/speculative selection is deliberately unavailable.
    mode: Literal["standard"] = "standard"


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    model: str = Field(min_length=1, max_length=128)
    prompt: str | None = Field(default=None, min_length=1, max_length=32768)
    messages: list[Message] | None = Field(default=None, min_length=1, max_length=64)
    max_tokens: int = Field(default=64, ge=1, le=512)
    temperature: float = Field(default=0.0, ge=0, le=2)
    seed: int = Field(default=0, ge=0, le=2**32 - 2)
    stream: bool = False
    timeout_seconds: float = Field(default=60.0, ge=0.1, le=300)
    optimization: Optimization = Field(default_factory=Optimization)

    @model_validator(mode="after")
    def exactly_one_input(self):
        if (self.prompt is None) == (self.messages is None):
            raise ValueError("Provide exactly one of prompt or messages")
        total = (
            len(self.prompt.encode())
            if self.prompt is not None
            else sum(len(m.content.encode()) for m in self.messages or [])
        )
        if total > 32768:
            raise ValueError("Input exceeds 32768 UTF-8 bytes")
        return self
