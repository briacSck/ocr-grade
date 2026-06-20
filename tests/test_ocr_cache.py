"""OCR cache tests with a fake in-memory backend (no network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ocr_grade.ocr import OCRBlock, OCRCache, OCRResult, PageMeta


class FakeBackend:
    name = "fake"

    def __init__(self, fingerprint: str = "fake-model|{}", cost_usd: float = 0.001) -> None:
        self.cache_fingerprint = fingerprint
        self._cost = cost_usd
        self.calls = 0

    def transcribe(self, image_path: Path, page_meta: PageMeta) -> OCRResult:
        self.calls += 1
        return OCRResult(
            markdown_text=f"# Page {page_meta.page_number}",
            blocks=[OCRBlock(type="heading", text="Q1", confidence=0.9)],
            raw_response={"stub": True},
            cost_usd=self._cost,
            latency_ms=1.0,
        )


def _write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


META = PageMeta(page_number=1, exam_sha="deadbeef", course="PE101")


def test_miss_then_hit(tmp_path: Path) -> None:
    backend = FakeBackend()
    cache = OCRCache(tmp_path)
    img = _write(tmp_path / "page.png", b"image-bytes-1")

    first = cache.get_or_call(backend, img, META)
    second = cache.get_or_call(backend, img, META)

    assert backend.calls == 1  # second served from cache
    assert cache.misses == 1
    assert cache.hits == 1
    assert first == second
    assert second.blocks[0].type == "heading"


def test_cost_accumulation(tmp_path: Path) -> None:
    backend = FakeBackend(cost_usd=0.001)
    cache = OCRCache(tmp_path)
    img1 = _write(tmp_path / "p1.png", b"bytes-1")
    img2 = _write(tmp_path / "p2.png", b"bytes-2")

    cache.get_or_call(backend, img1, META)
    cache.get_or_call(backend, img2, META)
    assert cache.misses == 2
    assert cache.total_cost_usd == pytest.approx(0.002)

    # re-calling the first is a cache hit -> no additional cost
    cache.get_or_call(backend, img1, META)
    assert cache.total_cost_usd == pytest.approx(0.002)
    assert cache.hits == 1


def test_fingerprint_busts_the_key(tmp_path: Path) -> None:
    cache = OCRCache(tmp_path)
    img = _write(tmp_path / "page.png", b"same-bytes")

    a = FakeBackend(fingerprint="mistral-ocr-latest|{}")
    b = FakeBackend(fingerprint="mistral-ocr-other|{}")
    cache.get_or_call(a, img, META)
    cache.get_or_call(b, img, META)  # different model -> fresh miss

    assert a.calls == 1
    assert b.calls == 1
    assert cache.misses == 2
    assert cache.hits == 0


def test_unicode_text_round_trips(tmp_path: Path) -> None:
    """OCR output with non-Latin-1 chars (math superscripts, arrows) must cache
    and reload intact. On Windows, write_text/read_text default to cp1252 and
    would raise UnicodeEncodeError here without an explicit utf-8 encoding."""

    class UnicodeBackend(FakeBackend):
        def transcribe(self, image_path: Path, page_meta: PageMeta) -> OCRResult:
            self.calls += 1
            return OCRResult(
                markdown_text="x⁰ → y ≡ limit",  # superscript 0, →, ≡
                blocks=[OCRBlock(type="paragraph", text="∑", confidence=0.9)],  # ∑
                raw_response={"stub": True},
                cost_usd=self._cost,
                latency_ms=1.0,
            )

    backend = UnicodeBackend()
    img = _write(tmp_path / "page.png", b"unicode-page")

    OCRCache(tmp_path).get_or_call(backend, img, META)
    reloaded = OCRCache(tmp_path).get_or_call(backend, img, META)

    assert backend.calls == 1  # second served from disk
    assert reloaded.markdown_text == "x⁰ → y ≡ limit"
    assert reloaded.blocks[0].text == "∑"


def test_persisted_json_round_trips_across_instances(tmp_path: Path) -> None:
    backend = FakeBackend()
    img = _write(tmp_path / "page.png", b"persist-me")

    OCRCache(tmp_path).get_or_call(backend, img, META)
    assert backend.calls == 1

    fresh = OCRCache(tmp_path)
    result = fresh.get_or_call(backend, img, META)
    assert backend.calls == 1  # served from disk, backend untouched
    assert fresh.hits == 1
    assert result.markdown_text == "# Page 1"
    assert result.blocks[0].confidence == 0.9
