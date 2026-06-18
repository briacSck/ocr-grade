"""End-to-end pipeline tests with injected fakes (no network)."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from ocr_grade import pipeline
from ocr_grade.config import Settings
from ocr_grade.ingestion import discover
from ocr_grade.ocr.base import OCRResult, PageMeta


class FakeBackend:
    name = "fake"
    cache_fingerprint = "fake-model|{}"

    def __init__(self, markdown: str = "# Q1\n\nAnswer line.", cost: float = 0.002) -> None:
        self.markdown = markdown
        self.cost = cost
        self.calls = 0

    def transcribe(self, image_path: Path, page_meta: PageMeta) -> OCRResult:
        self.calls += 1
        return OCRResult(markdown_text=self.markdown, cost_usd=self.cost)


class RaisingBackend(FakeBackend):
    def transcribe(self, image_path: Path, page_meta: PageMeta) -> OCRResult:
        raise RuntimeError("backend boom")


class FakeHeader:
    def read_header(self, header_png: bytes) -> str:
        return "SID: 1234567"


def _make_settings(tmp_path: Path, pages: int = 2) -> Settings:
    scans = tmp_path / "scans"
    scans.mkdir()
    c = canvas.Canvas(str(scans / "PE101.pdf"), pagesize=letter)
    for i in range(pages):
        # Draw below the masked header band so each page's masked image differs
        # (identical masked bytes would dedupe in the content-addressed cache).
        c.drawString(72, 400, f"Scanned body page {i + 1}")
        c.showPage()
    c.save()

    return Settings(
        input_dir=scans,
        output_dir=tmp_path / "out",
        cache_dir=tmp_path / "cache",
        course_preset="PE101",
        dpi=150,
        mistral={"api_key": "test", "model": "mistral-ocr-test"},
        redaction={"regex_patterns": [r"SID[:\s]*\d{7,10}"]},
        preprocess_steps={"deskew": False, "denoise": False, "contrast": False},
        mistral_price_per_page=0.001,
    )


def test_run_batch_produces_pdf_and_report(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)

    report = pipeline.run_batch(settings, backend=FakeBackend(), header_ocr=FakeHeader())

    assert report.pages_processed == 2
    assert report.total_cost_usd == pytest.approx(0.004)
    assert report.model == "mistral-ocr-test"
    assert len(report.outputs) == 1
    assert report.outputs[0].name == "PE101_PE101_1234567.pdf"
    with fitz.open(report.outputs[0]) as doc:
        assert doc.page_count == 4  # 2 scans interleaved with 2 transcripts

    report_md = (settings.output_dir / "run_report.md").read_text()
    assert "mistral-ocr-test" in report_md
    assert "0.0040" in report_md


def test_run_batch_records_failures_and_continues(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)

    report = pipeline.run_batch(settings, backend=RaisingBackend(), header_ocr=FakeHeader())

    assert len(report.failures) == 2
    assert all("boom" in f.reason for f in report.failures)
    assert report.outputs == []


def test_estimate_processes_only_first_page(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    backend = FakeBackend()

    est = pipeline.estimate(settings, backend=backend, header_ocr=FakeHeader())

    assert est.total_pages == 2
    assert est.estimated_cost_usd == pytest.approx(0.002)  # price 0.001 * 2 pages
    assert est.projected_wall_seconds >= 0
    assert backend.calls == 1  # only page 1 transcribed


def test_purge_batch_removes_artifacts_and_cache(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    backend = FakeBackend()
    pipeline.run_batch(settings, backend=backend, header_ocr=FakeHeader())

    sha = discover(settings.input_dir)[0].sha256
    exam_dir = Path(settings.cache_dir) / sha
    assert exam_dir.exists()
    ocr_entries = list((Path(settings.cache_dir) / "ocr").glob("*.json"))
    assert ocr_entries

    deleted = pipeline.purge_batch(settings, sha, backend=backend)

    assert not exam_dir.exists()
    assert any(p.suffix == ".json" for p in deleted)
    assert list((Path(settings.cache_dir) / "ocr").glob("*.json")) == []
