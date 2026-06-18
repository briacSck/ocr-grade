"""OCR backend interface, cache, and the Mistral OCR implementation."""

from .base import OCRBackend, OCRBlock, OCRResult, PageMeta
from .cache import OCRCache, get_or_call

__all__ = [
    "OCRBackend",
    "OCRBlock",
    "OCRResult",
    "PageMeta",
    "OCRCache",
    "get_or_call",
]
