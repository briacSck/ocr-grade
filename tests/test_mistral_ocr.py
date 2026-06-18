"""Mistral OCR backend tests using respx to mock the HTTP endpoint (no network)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from mistralai.client.errors.sdkerror import SDKError

from ocr_grade.config import Settings
from ocr_grade.ocr.base import PageMeta
from ocr_grade.ocr.mistral import MistralOCRBackend, _parse_blocks

OCR_URL = "https://api.mistral.ai/v1/ocr"
META = PageMeta(page_number=1, exam_sha="abc", course="PE101")


def _settings(price: float = 0.001) -> Settings:
    return Settings(
        input_dir=".",
        output_dir=".",
        cache_dir=".",
        course_preset="PE101",
        mistral={"api_key": "test-key", "model": "mistral-ocr-latest"},
        mistral_price_per_page=price,
    )


def _ocr_body(markdown: str) -> dict[str, Any]:
    return {
        "pages": [
            {
                "index": 0,
                "markdown": markdown,
                "images": [],
                "dimensions": {"dpi": 150, "height": 2200, "width": 1700},
            }
        ],
        "model": "mistral-ocr-2512",
        "usage_info": {"pages_processed": 1, "doc_size_bytes": 1000},
    }


def _backend() -> MistralOCRBackend:
    return MistralOCRBackend(_settings(), sleep=lambda _: None)


def _image(tmp_path: Path) -> Path:
    path = tmp_path / "page.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n fake png bytes")
    return path


@respx.mock
def test_happy_path(tmp_path: Path) -> None:
    md = "# Q1\n\nAnswer text\n\n- a\n- b"
    route = respx.post(OCR_URL).mock(return_value=httpx.Response(200, json=_ocr_body(md)))

    result = _backend().transcribe(_image(tmp_path), META)

    assert route.call_count == 1
    assert result.markdown_text == md
    assert [b.type for b in result.blocks] == ["heading", "paragraph", "list"]
    assert result.blocks[0].text == "Q1"
    assert result.blocks[2].text == "a\nb"
    assert all(b.confidence is None for b in result.blocks)
    assert result.cost_usd == 0.001
    assert result.latency_ms >= 0


@respx.mock
def test_retries_on_429_with_retry_after(tmp_path: Path) -> None:
    route = respx.post(OCR_URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}, json={"message": "slow down"}),
            httpx.Response(200, json=_ocr_body("# ok")),
        ]
    )

    result = _backend().transcribe(_image(tmp_path), META)

    assert route.call_count == 2
    assert result.markdown_text == "# ok"


@respx.mock
def test_permanent_5xx_raises_after_max_attempts(tmp_path: Path) -> None:
    route = respx.post(OCR_URL).mock(return_value=httpx.Response(500, text="boom"))

    with pytest.raises(SDKError):
        _backend().transcribe(_image(tmp_path), META)

    assert route.call_count == 5


def test_parse_blocks_mixed_markdown() -> None:
    md = "# Heading\n\nA paragraph.\n\n1. one\n2. two\n\n- x\n- y"
    blocks = _parse_blocks(md)

    assert [b.type for b in blocks] == ["heading", "paragraph", "list", "list"]
    assert blocks[0].text == "Heading"
    assert blocks[1].text == "A paragraph."
    assert blocks[2].text == "one\ntwo"
    assert blocks[3].text == "x\ny"


def test_cache_fingerprint_includes_model() -> None:
    backend = _backend()
    assert backend.cache_fingerprint.startswith("mistral-ocr-latest|")
    assert "include_image_base64" in backend.cache_fingerprint


@pytest.mark.skipif(
    not os.environ.get("MISTRAL_API_KEY"),
    reason="integration test requires MISTRAL_API_KEY",
)
def test_integration_real_call(tmp_path: Path) -> None:
    import numpy as np
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    from ocr_grade.ingestion import discover
    from ocr_grade.preprocess import rasterize

    src = tmp_path / "scans"
    src.mkdir()
    c = canvas.Canvas(str(src / "PE101.pdf"), pagesize=letter)
    c.drawString(72, 720, "Integration check 123")
    c.showPage()
    c.save()
    exam = discover(src)[0]
    page = rasterize(exam, dpi=150, cache_dir=tmp_path / "cache")[0]
    assert page.path is not None
    assert isinstance(np.asarray(page.image), np.ndarray)

    backend = MistralOCRBackend(_settings())
    result = backend.transcribe(page.path, META)
    assert isinstance(result.markdown_text, str)
