"""Single-user web UI for ocr-grade (FastAPI).

Run with: ``uvicorn ocr_grade.web.app:app``.
"""

from .app import app

__all__ = ["app"]
