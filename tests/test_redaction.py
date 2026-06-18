"""Redaction tests with a stubbed header OCR (no real student data, no network)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from ocr_grade.config import Settings
from ocr_grade.preprocess import PageImage
from ocr_grade.redaction import HEADER_BAND_FRACTION, mask

PATTERNS = [r"SID[:\s]*\d{7,10}", r"Name[:\s]*[A-Z][a-z]+ [A-Z][a-z]+"]


class FakeHeaderOCR:
    """Returns canned header text regardless of the image bytes."""

    def __init__(self, text: str = "Name: John Doe\nSID: 12345678") -> None:
        self.text = text

    def read_header(self, header_png: bytes) -> str:
        return self.text


def _make_settings(tmp_path: Path, header_box: tuple[int, int, int, int] | None) -> Settings:
    return Settings(
        input_dir=tmp_path,
        output_dir=tmp_path,
        cache_dir=tmp_path,
        course_preset="PE101",
        redaction={"header_box": header_box, "regex_patterns": PATTERNS},
        mistral={"api_key": "test-key"},
    )


def _make_page(tmp_path: Path, h: int = 600, w: int = 400) -> PageImage:
    image = np.full((h, w, 3), 255, dtype=np.uint8)  # white page
    # draw a non-white header strip so masking is visibly distinguishable
    image[0 : int(h * HEADER_BAND_FRACTION), :] = 128
    path = tmp_path / "cache" / "abc123" / "page_1.png"
    return PageImage(page_number=1, image=image, path=path)


def test_regex_match_masks_band_and_records_identity(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path, header_box=None)
    page = _make_page(tmp_path)

    masked = mask(page, settings, header_ocr=FakeHeaderOCR())

    band = int(page.image.shape[0] * HEADER_BAND_FRACTION)
    # header band fully black
    assert np.all(masked.image[0:band, :] == 0)
    # body well below the band untouched (still white)
    assert np.all(masked.image[band + 10 :, :] == 255)
    # identity captured
    assert "Name: John Doe" in masked.identity_strings
    assert "SID: 12345678" in masked.identity_strings
    assert any(r.reason == "regex" for r in masked.regions)


def test_sidecar_written_and_round_trips(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path, header_box=None)
    page = _make_page(tmp_path)

    masked = mask(page, settings, header_ocr=FakeHeaderOCR())

    assert masked.sidecar_path is not None
    assert masked.sidecar_path.name == "page_1.identity.json"
    data = json.loads(masked.sidecar_path.read_text())
    assert data["page_number"] == 1
    assert "SID: 12345678" in data["identity_strings"]
    assert len(data["regions"]) >= 1


def test_no_match_leaves_body_unmasked_and_no_identity(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path, header_box=None)
    page = _make_page(tmp_path)

    masked = mask(page, settings, header_ocr=FakeHeaderOCR(text="nothing identifying here"))

    assert masked.identity_strings == []
    assert not any(r.reason == "regex" for r in masked.regions)
    # nothing masked -> the original 128 header strip survives
    assert np.any(masked.image == 128)


def test_configured_header_box_is_masked(tmp_path: Path) -> None:
    box = (0, 0, 400, 80)
    settings = _make_settings(tmp_path, header_box=box)
    page = _make_page(tmp_path)

    masked = mask(page, settings, header_ocr=FakeHeaderOCR(text="nothing"))

    assert np.all(masked.image[0:80, :] == 0)
    assert any(r.reason == "header_box" for r in masked.regions)


@pytest.mark.parametrize("text", ["", "Random scribbles 42"])
def test_blank_header_text_is_safe(tmp_path: Path, text: str) -> None:
    settings = _make_settings(tmp_path, header_box=None)
    page = _make_page(tmp_path)

    masked = mask(page, settings, header_ocr=FakeHeaderOCR(text=text))

    assert masked.identity_strings == []
