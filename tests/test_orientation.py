"""Orientation detection + normalization tests (no network).

The geometric axis test (`text_is_horizontal`) is exercised on synthetic band
images; the flip resolution in `detect_orientation` uses a fake header OCR that
only "sees" identity when the real header band lands at the top.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ocr_grade.config import Settings
from ocr_grade.preprocess import PageImage, rotate_image, text_is_horizontal
from ocr_grade.redaction import detect_orientation

PATTERNS = [r"SID[:\s]*\d{7,10}"]


def _settings(tmp_path: Path, *, auto_orient: bool = True) -> Settings:
    return Settings(
        input_dir=tmp_path,
        output_dir=tmp_path,
        cache_dir=tmp_path,
        course_preset="PE101",
        redaction={"regex_patterns": PATTERNS, "auto_orient": auto_orient},
        mistral={"api_key": "test-key"},
    )


class BandAwareHeaderOCR:
    """Returns the SID only when the cropped band is mostly dark (the marker).

    The test page is white with a dark bar along one edge; whichever rotation
    puts that bar in the top header band is the upright one.
    """

    def read_header(self, header_png: bytes) -> str:
        arr = cv2.imdecode(np.frombuffer(header_png, np.uint8), cv2.IMREAD_GRAYSCALE)
        return "SID: 1234567" if float(arr.mean()) < 128 else "no identity here"


def _page_with_marker_at_bottom(h: int = 600, w: int = 400) -> PageImage:
    """White page with a full-width dark bar across the BOTTOM edge.

    Upright therefore requires a 180 rotation (bar -> top). The full-width bar
    also makes the text-line axis horizontal, so candidates are (0, 180).
    """
    image = np.full((h, w, 3), 255, dtype=np.uint8)
    image[int(h * 0.9) :, :] = 20  # dark bar, bottom 10%
    return PageImage(page_number=1, image=image, path=None)


def test_text_is_horizontal_detects_axis() -> None:
    horizontal = np.full((600, 400, 3), 255, dtype=np.uint8)
    horizontal[280:320, :] = 0  # a wide horizontal bar -> rows band strongly
    assert text_is_horizontal(horizontal) is True
    # rotate 90 -> the bar is now vertical
    assert text_is_horizontal(rotate_image(horizontal, 90)) is False


def test_rotate_image_roundtrip() -> None:
    img = np.arange(2 * 3 * 3, dtype=np.uint8).reshape(2, 3, 3)
    assert np.array_equal(rotate_image(img, 0), img)
    assert np.array_equal(rotate_image(rotate_image(img, 90), 270), img)
    assert np.array_equal(rotate_image(img, 180), rotate_image(rotate_image(img, 90), 90))


def test_detect_orientation_resolves_upside_down(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    page = _page_with_marker_at_bottom()
    assert detect_orientation(page, settings, header_ocr=BandAwareHeaderOCR()) == 180


def test_detect_orientation_noop_when_already_upright(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    image = np.full((600, 400, 3), 255, dtype=np.uint8)
    image[: int(600 * 0.1), :] = 20  # dark bar already at TOP
    page = PageImage(page_number=1, image=image, path=None)
    assert detect_orientation(page, settings, header_ocr=BandAwareHeaderOCR()) == 0


def test_detect_orientation_disabled_returns_zero(tmp_path: Path) -> None:
    settings = _settings(tmp_path, auto_orient=False)
    page = _page_with_marker_at_bottom()
    assert detect_orientation(page, settings, header_ocr=BandAwareHeaderOCR()) == 0


def test_detect_orientation_ambiguous_returns_zero(tmp_path: Path) -> None:
    """A header OCR that always finds identity (tie) must not rotate."""
    settings = _settings(tmp_path)

    class AlwaysIdentity:
        def read_header(self, header_png: bytes) -> str:
            return "SID: 1234567"

    page = _page_with_marker_at_bottom()
    assert detect_orientation(page, settings, header_ocr=AlwaysIdentity()) == 0
