"""Tests for markdown cleanup and prompt/answer splitting (no network)."""

from __future__ import annotations

from ocr_grade.ocr.base import OCRResult
from ocr_grade.postprocess import clean_text, split_prompt_and_answer


def _split(md: str) -> tuple[str | None, str]:
    return split_prompt_and_answer(clean_text(OCRResult(markdown_text=md)))


def test_clean_text_normalizes_whitespace_and_blank_runs() -> None:
    raw = "# Q1   \n\n\n\nThe  answer\tis   42.   \n\n\n"
    cleaned = clean_text(OCRResult(markdown_text=raw))

    assert cleaned.markdown_text == "# Q1\n\nThe answer is 42."
    # No trailing whitespace and at most one blank line between blocks.
    assert "\n\n\n" not in cleaned.markdown_text
    assert all(line == line.rstrip() for line in cleaned.markdown_text.split("\n"))


def test_clean_text_normalizes_block_text() -> None:
    result = OCRResult(
        markdown_text="A  paragraph.",
        blocks=[{"type": "paragraph", "text": "A  paragraph.  "}],  # type: ignore[list-item]
    )
    cleaned = clean_text(result)
    assert cleaned.blocks[0].text == "A paragraph."


def test_heading_plus_paragraph() -> None:
    prompt, answer = _split("# Question 1\n\nThe answer is 42.")
    assert prompt == "# Question 1"
    assert answer == "The answer is 42."


def test_no_heading_is_all_answer() -> None:
    md = "The mitochondria is the powerhouse of the cell."
    prompt, answer = _split(md)
    assert prompt is None
    assert answer == md


def test_prompt_only_heading_page() -> None:
    prompt, answer = _split("## Problem 3")
    assert prompt == "## Problem 3"
    assert answer == ""


def test_printed_paragraph_prompt_plus_answer() -> None:
    prompt, answer = _split("Define osmosis:\n\nOsmosis is movement of water.")
    assert prompt == "Define osmosis:"
    assert answer == "Osmosis is movement of water."


def test_question_mark_paragraph_is_prompt() -> None:
    prompt, answer = _split("What is entropy?\n\nIt is disorder.")
    assert prompt == "What is entropy?"
    assert answer == "It is disorder."


def test_h4_heading_is_not_a_prompt() -> None:
    md = "#### Note\n\nbody"
    prompt, answer = _split(md)
    assert prompt is None
    assert answer == md


def test_empty_page() -> None:
    prompt, answer = _split("")
    assert prompt is None
    assert answer == ""
