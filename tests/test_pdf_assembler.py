"""Tests for the interleaved manuscript+transcript assembler (no network)."""

from __future__ import annotations

import json
from pathlib import Path

import fitz
import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from ocr_grade.ingestion import discover
from ocr_grade.pdf_assembler import PageTranscript, _safe, build_interleaved


@pytest.fixture
def exam(tmp_path: Path):
    src = tmp_path / "scans"
    src.mkdir()
    c = canvas.Canvas(str(src / "PE101.pdf"), pagesize=letter)
    c.drawString(72, 720, "Scanned page one")
    c.showPage()
    c.drawString(72, 720, "Scanned page two")
    c.showPage()
    c.save()
    return discover(src)[0]


def _transcripts() -> list[PageTranscript]:
    return [
        PageTranscript(page_number=1, prompt="# Question 1", answer="Answer one."),
        PageTranscript(page_number=2, prompt=None, answer="Answer two."),
    ]


def test_golden_interleaved_text(exam, tmp_path: Path, snapshot) -> None:
    out = build_interleaved(exam, _transcripts(), tmp_path / "out", student_id="30412345")

    assert len(out) == 1
    assert out[0].name == "PE101_PE101_30412345.pdf"
    with fitz.open(out[0]) as doc:
        assert doc.page_count == 4  # 2 scans interleaved with 2 transcripts
        text = "\n--PAGE--\n".join(page.get_text() for page in doc)
    snapshot.assert_match(text, "interleaved.txt")


def test_student_id_from_sidecar(exam, tmp_path: Path) -> None:
    sidecar = tmp_path / "page.identity.json"
    sidecar.write_text(json.dumps({"identity_strings": ["Jane Doe", "3041234"]}))

    out = build_interleaved(exam, _transcripts(), tmp_path / "out", identity_sidecars=[sidecar])

    assert out[0].name == "PE101_PE101_3041234.pdf"


def test_size_guard_splits_into_two_parts(exam, tmp_path: Path) -> None:
    out = build_interleaved(
        exam, _transcripts(), tmp_path / "out", student_id="30412345", max_bytes=2000
    )

    assert [p.name for p in out] == [
        "PE101_PE101_30412345_part1.pdf",
        "PE101_PE101_30412345_part2.pdf",
    ]
    for part in out:
        with fitz.open(part) as doc:
            assert doc.page_count >= 2


def test_filename_sanitize() -> None:
    assert _safe("PE 101_mid term_30412345") == "PE_101_mid_term_30412345"
    assert " " not in _safe("a/b c:d")
