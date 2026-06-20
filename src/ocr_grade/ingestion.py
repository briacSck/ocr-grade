"""Discover and validate input exam PDFs.

`discover(input_dir) -> list[ExamFile]` records, per PDF: path, page_count,
sha256, detected course (from filename), an estimated native scan DPI, and a
validation status. Corrupt PDFs, scans below ~150 DPI, and PDFs over Mistral's
OCR limits are flagged (not raised) so the caller can report them all at once.

Mistral OCR limits (see https://docs.mistral.ai/resources/known-limitations):
whole-PDF uploads are capped at 50 MB and 1000 pages; a single rasterized image
is capped at 20 MB (enforced at rasterization time in `preprocess.rasterize`).
"""

from __future__ import annotations

import json
import re
from enum import StrEnum
from pathlib import Path

import fitz  # PyMuPDF
from pydantic import BaseModel

from .utils import sha256_file

MAX_PAGES = 1000
MAX_PDF_BYTES = 50 * 1024 * 1024
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MIN_NATIVE_DPI = 150

# Pulls a course code like "PE101" or "P156" out of a filename stem.
COURSE_RE = re.compile(r"(?P<course>[A-Z]{1,4}\s?\d{2,3}[A-Z]?)")


class IngestionError(RuntimeError):
    """Raised for unrecoverable ingestion/rasterization failures."""


class ValidationStatus(StrEnum):
    OK = "ok"
    CORRUPT = "corrupt"
    DPI_TOO_LOW = "dpi_too_low"
    TOO_MANY_PAGES = "too_many_pages"
    FILE_TOO_LARGE = "file_too_large"


class ExamFile(BaseModel):
    path: Path
    page_count: int
    sha256: str
    course: str | None
    status: ValidationStatus
    message: str | None = None
    native_dpi: float | None = None


def _detect_course(stem: str) -> str | None:
    match = COURSE_RE.search(stem)
    if match is None:
        return None
    return match.group("course").replace(" ", "")


def _estimate_native_dpi(doc: fitz.Document) -> float | None:
    """Estimate the lowest embedded-scan DPI across pages.

    For each page, take the widest embedded raster image and divide its pixel
    width by the page width in inches. Pages with no embedded raster (vector or
    pure-text PDFs) are skipped so they don't get false-flagged as low-DPI.
    Returns None if no page has an embedded raster image.
    """
    per_page: list[float] = []
    for page in doc:
        page_width_in = page.rect.width / 72.0
        if page_width_in <= 0:
            continue
        widest_px = 0
        for img in page.get_images(full=True):
            xref = img[0]
            extracted = doc.extract_image(xref)
            widest_px = max(widest_px, extracted.get("width", 0))
        if widest_px > 0:
            per_page.append(widest_px / page_width_in)
    if not per_page:
        return None
    return min(per_page)


def discover(
    input_dir: str | Path,
    *,
    cache_dir: str | Path | None = None,
    min_native_dpi: int = MIN_NATIVE_DPI,
) -> list[ExamFile]:
    """Scan ``input_dir`` for PDFs and return a validated record per file.

    When ``cache_dir`` is given, a ``manifest.json`` of the records is written
    there as a side effect.
    """
    input_dir = Path(input_dir)
    records: list[ExamFile] = []

    for pdf_path in sorted(input_dir.glob("*.pdf")):
        sha = sha256_file(pdf_path)
        course = _detect_course(pdf_path.stem)
        try:
            doc = fitz.open(pdf_path)
        except Exception as exc:  # noqa: BLE001 - any open failure is "corrupt"
            records.append(
                ExamFile(
                    path=pdf_path,
                    page_count=0,
                    sha256=sha,
                    course=course,
                    status=ValidationStatus.CORRUPT,
                    message=f"Could not open PDF: {exc}",
                )
            )
            continue

        with doc:
            page_count = doc.page_count
            size_bytes = pdf_path.stat().st_size
            native_dpi = _estimate_native_dpi(doc)

        status = ValidationStatus.OK
        message: str | None = None
        if page_count > MAX_PAGES:
            status = ValidationStatus.TOO_MANY_PAGES
            message = (
                f"{page_count} pages exceeds Mistral's {MAX_PAGES}-page limit; "
                "split the PDF into smaller files."
            )
        elif size_bytes > MAX_PDF_BYTES:
            status = ValidationStatus.FILE_TOO_LARGE
            message = (
                f"{size_bytes / 1024 / 1024:.1f} MB exceeds Mistral's "
                f"{MAX_PDF_BYTES // 1024 // 1024} MB limit; lower `dpi` or split the PDF."
            )
        elif native_dpi is not None and native_dpi < min_native_dpi:
            status = ValidationStatus.DPI_TOO_LOW
            message = (
                f"Estimated scan resolution ~{native_dpi:.0f} DPI is below the "
                f"{min_native_dpi} DPI minimum; rescan at higher resolution."
            )

        records.append(
            ExamFile(
                path=pdf_path,
                page_count=page_count,
                sha256=sha,
                course=course,
                status=status,
                message=message,
                native_dpi=native_dpi,
            )
        )

    if cache_dir is not None:
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        manifest = [r.model_dump(mode="json") for r in records]
        (cache_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return records
