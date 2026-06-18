"""OCR backend protocol and result types.

Defines the backend-agnostic seam (`OCRBackend`) that the page transcription
pipeline talks to, plus the structured result it returns. Mistral is currently
the only concrete backend (see `ocr/mistral.py`), but keeping the Protocol makes
a future swap a drop-in change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel


class PageMeta(BaseModel):
    """Contextual metadata passed to a backend (logging/diagnostics).

    Not part of the cache key: identical image bytes transcribe identically
    regardless of which exam/page they came from.
    """

    page_number: int
    exam_sha: str | None = None
    course: str | None = None


class OCRBlock(BaseModel):
    type: Literal["heading", "paragraph", "list"]
    text: str
    confidence: float | None = None


class OCRResult(BaseModel):
    markdown_text: str
    blocks: list[OCRBlock] = []
    raw_response: dict[str, Any] | None = None
    cost_usd: float = 0.0
    latency_ms: float = 0.0


class OCRBackend(Protocol):
    """Structural interface every OCR backend implements."""

    name: str
    # Model name + serialized params (e.g. "mistral-ocr-latest|{...}"). Folded
    # into the cache key so a model/param change never serves a stale result.
    cache_fingerprint: str

    def transcribe(self, image_path: Path, page_meta: PageMeta) -> OCRResult: ...
