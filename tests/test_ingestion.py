"""Ingestion tests against synthetic reportlab PDFs (no real student data)."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from ocr_grade.ingestion import ValidationStatus, discover


def _make_text_pdf(path: Path, pages: int = 3) -> Path:
    c = canvas.Canvas(str(path), pagesize=letter)
    for n in range(pages):
        c.drawString(72, 720, f"Synthetic exam page {n + 1}")
        c.showPage()
    c.save()
    return path


def _make_lowdpi_pdf(path: Path) -> Path:
    """A full-page scan rendered from a tiny image -> very low native DPI."""
    tiny = Image.new("RGB", (100, 130), "white")
    width_pt, height_pt = letter
    c = canvas.Canvas(str(path), pagesize=letter)
    c.drawImage(ImageReader(tiny), 0, 0, width=width_pt, height=height_pt)
    c.showPage()
    c.save()
    return path


def test_discover_text_pdf(tmp_path: Path) -> None:
    _make_text_pdf(tmp_path / "PE101_exam.pdf", pages=3)

    records = discover(tmp_path)

    assert len(records) == 1
    rec = records[0]
    assert rec.status is ValidationStatus.OK
    assert rec.page_count == 3
    assert rec.course == "PE101"
    assert len(rec.sha256) == 64


def test_sha256_is_stable(tmp_path: Path) -> None:
    _make_text_pdf(tmp_path / "PE101_exam.pdf", pages=2)

    first = discover(tmp_path)[0].sha256
    second = discover(tmp_path)[0].sha256

    assert first == second


def test_corrupt_pdf_is_flagged_not_raised(tmp_path: Path) -> None:
    (tmp_path / "bad.pdf").write_bytes(b"this is not a pdf")

    records = discover(tmp_path)

    assert len(records) == 1
    assert records[0].status is ValidationStatus.CORRUPT


def test_low_dpi_pdf_is_flagged(tmp_path: Path) -> None:
    _make_lowdpi_pdf(tmp_path / "P156_lowres.pdf")

    rec = discover(tmp_path)[0]

    assert rec.status is ValidationStatus.DPI_TOO_LOW
    assert rec.native_dpi is not None and rec.native_dpi < 150


def test_manifest_is_written_and_round_trips(tmp_path: Path) -> None:
    src = tmp_path / "scans"
    src.mkdir()
    cache = tmp_path / "cache"
    _make_text_pdf(src / "PE101_exam.pdf", pages=1)

    records = discover(src, cache_dir=cache)

    manifest_path = cache / "manifest.json"
    assert manifest_path.exists()
    data = json.loads(manifest_path.read_text())
    assert len(data) == 1
    assert data[0]["sha256"] == records[0].sha256
    assert data[0]["status"] == "ok"
