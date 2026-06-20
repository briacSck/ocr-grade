"""Content-addressed local cache for OCR results.

Keys each result by sha256(image_bytes) + backend.name + backend.cache_fingerprint
(model name + serialized params) and stores the `OCRResult` as JSON, so identical
pages are never re-billed and a model/param change transparently misses.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from ..utils import sha256_bytes
from .base import OCRBackend, OCRResult, PageMeta


def _cache_key(image_bytes: bytes, backend: OCRBackend) -> str:
    raw = f"{sha256_bytes(image_bytes)}|{backend.name}|{backend.cache_fingerprint}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class OCRCache:
    """A directory-backed OCR result cache that accumulates cost/hit stats."""

    def __init__(self, cache_dir: str | Path) -> None:
        self.dir = Path(cache_dir) / "ocr"
        self.total_cost_usd = 0.0
        self.hits = 0
        self.misses = 0

    def get_or_call(
        self,
        backend: OCRBackend,
        image_path: str | Path,
        meta: PageMeta,
    ) -> OCRResult:
        """Return a cached `OCRResult` for the image, or call the backend and store it."""
        image_path = Path(image_path)
        image_bytes = image_path.read_bytes()
        key = _cache_key(image_bytes, backend)
        entry = self.dir / f"{key}.json"

        if entry.exists():
            self.hits += 1
            return OCRResult.model_validate_json(entry.read_text(encoding="utf-8"))

        result = backend.transcribe(image_path, meta)
        self.misses += 1
        self.total_cost_usd += result.cost_usd

        self.dir.mkdir(parents=True, exist_ok=True)
        entry.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return result


def get_or_call(
    backend: OCRBackend,
    image_path: str | Path,
    meta: PageMeta,
    cache_dir: str | Path,
) -> OCRResult:
    """One-shot convenience wrapper around `OCRCache.get_or_call`.

    Callers that need cost/hit accumulation across a batch should hold a single
    `OCRCache` instance instead.
    """
    return OCRCache(cache_dir).get_or_call(backend, image_path, meta)
