"""Preprocess tests against synthetic reportlab PDFs (no real student data)."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from ocr_grade.config import PreprocessStepsSettings
from ocr_grade.ingestion import discover
from ocr_grade.preprocess import clean, rasterize


def _make_text_pdf(path: Path, pages: int = 3) -> Path:
    c = canvas.Canvas(str(path), pagesize=letter)
    for n in range(pages):
        c.drawString(72, 720, f"Synthetic exam page {n + 1}")
        c.showPage()
    c.save()
    return path


def test_rasterize_writes_cached_pngs(tmp_path: Path) -> None:
    src = tmp_path / "scans"
    src.mkdir()
    cache = tmp_path / "cache"
    _make_text_pdf(src / "PE101_exam.pdf", pages=3)
    exam = discover(src)[0]

    pages = rasterize(exam, dpi=150, cache_dir=cache)

    assert len(pages) == 3
    assert [p.page_number for p in pages] == [1, 2, 3]
    for page in pages:
        assert page.path is not None
        assert page.path.exists()
        assert page.path.stat().st_size > 0
        assert page.image.ndim == 3


def test_clean_runs_with_all_steps(tmp_path: Path) -> None:
    src = tmp_path / "scans"
    src.mkdir()
    cache = tmp_path / "cache"
    _make_text_pdf(src / "PE101_exam.pdf", pages=1)
    exam = discover(src)[0]
    page = rasterize(exam, dpi=150, cache_dir=cache)[0]

    all_on = clean(page.image, PreprocessStepsSettings())

    assert all_on.shape == page.image.shape


def test_clean_with_each_step_disabled(tmp_path: Path) -> None:
    src = tmp_path / "scans"
    src.mkdir()
    cache = tmp_path / "cache"
    _make_text_pdf(src / "PE101_exam.pdf", pages=1)
    exam = discover(src)[0]
    page = rasterize(exam, dpi=150, cache_dir=cache)[0]

    for steps in (
        PreprocessStepsSettings(deskew=False),
        PreprocessStepsSettings(denoise=False),
        PreprocessStepsSettings(contrast=False),
        PreprocessStepsSettings(deskew=False, denoise=False, contrast=False),
    ):
        out = clean(page.image, steps)
        assert out.shape[:2] == page.image.shape[:2]
