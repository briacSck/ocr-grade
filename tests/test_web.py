"""Offline tests for the web UI (Starlette TestClient runs background tasks sync)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from ocr_grade import pipeline
from ocr_grade.ocr.base import OCRResult, PageMeta
from ocr_grade.web.settings import get_web_settings


class _FakeBackend:
    name = "fake"
    cache_fingerprint = "fake-model|{}"

    def transcribe(self, image_path: Path, page_meta: PageMeta) -> OCRResult:
        return OCRResult(markdown_text="# Q1\n\nAnswer line.", cost_usd=0.002)


def _exam_zip() -> bytes:
    pdf = io.BytesIO()
    c = canvas.Canvas(pdf, pagesize=letter)
    c.drawString(72, 400, "Scanned body page 1")
    c.showPage()
    c.save()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("PE101.pdf", pdf.getvalue())
    return buf.getvalue()


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("MISTRAL_API_KEY", "test")
    monkeypatch.setattr(pipeline, "_build_backend", lambda settings: _FakeBackend())
    monkeypatch.setattr(
        "ocr_grade.redaction.MistralHeaderOCR.read_header",
        lambda self, header_png: "SID: 1234567",
    )

    config = tmp_path / "config.yaml"
    config.write_text(
        "input_dir: ./in\n"
        "output_dir: ./out\n"
        "cache_dir: ./cache\n"
        "course_preset: PE101\n"
        "dpi: 150\n"
        "redaction:\n"
        "  regex_patterns:\n"
        "    - 'SID[:\\s]*\\d{7,10}'\n"
        "mistral:\n"
        "  model: mistral-ocr-test\n"
        "preprocess_steps:\n"
        "  deskew: false\n"
        "  denoise: false\n"
        "  contrast: false\n"
    )

    monkeypatch.setenv("OCR_GRADE_WEB_USER", "me")
    monkeypatch.setenv("OCR_GRADE_WEB_PASSWORD", "secret")
    monkeypatch.setenv("OCR_GRADE_WEB_BASE_CONFIG", str(config))
    monkeypatch.setenv("OCR_GRADE_WEB_WORKDIR", str(tmp_path / "web-work"))
    get_web_settings.cache_clear()

    from ocr_grade.web.app import app

    yield TestClient(app)
    get_web_settings.cache_clear()


def test_healthz_is_unauthenticated(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_index_requires_auth(client: TestClient) -> None:
    assert client.get("/").status_code == 401
    r = client.get("/", auth=("me", "secret"))
    assert r.status_code == 200
    assert "Upload" in r.text


def test_upload_runs_pipeline_and_serves_pdf(client: TestClient) -> None:
    r = client.post(
        "/batches",
        files={"archive": ("exams.zip", _exam_zip(), "application/zip")},
        auth=("me", "secret"),
    )
    assert r.status_code == 200  # followed the 303 redirect to the status page
    assert "done" in r.text
    assert "PE101_PE101_1234567.pdf" in r.text

    batch_id = r.url.path.rsplit("/", 1)[-1]

    dl = client.get(f"/batches/{batch_id}/files/PE101_PE101_1234567.pdf", auth=("me", "secret"))
    assert dl.status_code == 200
    assert dl.headers["content-type"] == "application/pdf"
    assert dl.content[:4] == b"%PDF"

    arc = client.get(f"/batches/{batch_id}/archive", auth=("me", "secret"))
    assert arc.status_code == 200
    assert arc.headers["content-type"] == "application/zip"


def test_traversal_filename_is_rejected(client: TestClient) -> None:
    r = client.post(
        "/batches",
        files={"archive": ("exams.zip", _exam_zip(), "application/zip")},
        auth=("me", "secret"),
    )
    batch_id = r.url.path.rsplit("/", 1)[-1]
    bad = client.get(f"/batches/{batch_id}/files/..%2f..%2fconfig.yaml", auth=("me", "secret"))
    assert bad.status_code == 404


def test_empty_zip_is_rejected(client: TestClient) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", b"no pdfs here")
    r = client.post(
        "/batches",
        files={"archive": ("exams.zip", buf.getvalue(), "application/zip")},
        auth=("me", "secret"),
    )
    assert r.status_code == 400
