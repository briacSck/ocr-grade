"""Markdown-aware cleanup and prompt/answer splitting.

Turns a raw `OCRResult` (markdown + heading/paragraph/list blocks) into a
normalized `CleanedPage`, then splits each page into the printed **prompt** and
the handwritten **answer** so the pdf_assembler can interleave them into a
Gradescope-ready transcript.

The splitter re-parses the cleaned markdown with markdown-it-py directly (a
light dep) rather than reusing `ocr.mistral._parse_blocks` — importing that
module would pull in the Mistral SDK + truststore at load time. Re-parsing also
exposes each block's HTML tag (`h1`/`h2`/`h3`) and source line-map, which lets us
honor the h1/h2/h3 rule exactly and slice the original markdown losslessly.
"""

from __future__ import annotations

import re

from markdown_it import MarkdownIt
from pydantic import BaseModel

from .ocr.base import OCRBlock, OCRResult

# A leading paragraph reads as a printed prompt (vs. a handwritten answer) when
# it opens with a question/problem cue. OCR carries no font signal, so this is a
# text-only heuristic — kept conservative so ordinary answer prose is not
# mistaken for a prompt.
_PROMPT_CUE = re.compile(r"(?i)^\s*(question|problem|part|exercise|prompt|section|q\.?\s*\d)\b")
_PROMPT_HEADING_TAGS = {"h1", "h2", "h3"}

_md = MarkdownIt()


class CleanedPage(BaseModel):
    """A page after whitespace/structure normalization.

    `markdown_text` is the canonical form the splitter operates on; `blocks`
    carries the OCR backend's structured blocks (with normalized text) through
    for any downstream that wants structure without re-parsing.
    """

    markdown_text: str
    blocks: list[OCRBlock] = []


def _collapse_inline_ws(text: str) -> str:
    """Collapse runs of horizontal whitespace (incl. tabs) to a single space."""
    return re.sub(r"[^\S\n]+", " ", text)


def _normalize_markdown(text: str) -> str:
    """Normalize whitespace while preserving markdown structure.

    Unifies newlines, collapses horizontal whitespace runs and trailing spaces,
    and limits blank runs to a single blank line — markers and block ordering
    are left untouched.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [_collapse_inline_ws(line).rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n")


def clean_text(ocr_result: OCRResult) -> CleanedPage:
    """Normalize an `OCRResult` into a `CleanedPage` (structure preserved)."""
    blocks = [
        block.model_copy(update={"text": _collapse_inline_ws(block.text).strip()})
        for block in ocr_result.blocks
    ]
    return CleanedPage(
        markdown_text=_normalize_markdown(ocr_result.markdown_text),
        blocks=blocks,
    )


def _looks_printed(text: str) -> bool:
    """Heuristic: does this leading paragraph read as a printed prompt?"""
    stripped = text.rstrip()
    return bool(_PROMPT_CUE.match(text)) or stripped.endswith(("?", ":"))


def split_prompt_and_answer(cleaned: CleanedPage) -> tuple[str | None, str]:
    """Split a cleaned page into its printed prompt and the answer.

    If the page opens with an h1/h2/h3 heading or a clearly printed-looking
    paragraph, that leading block is the prompt and the rest is the answer.
    Otherwise the whole page is the answer and the prompt is `None`. Returned
    values are markdown strings sliced from `cleaned.markdown_text`; the answer
    is `""` for a prompt-only page.

    Note: a heading level beyond h3 (rare in this OCR output) is treated as
    answer, and the ordered/bullet list distinction is irrelevant to the split.
    """
    text = cleaned.markdown_text
    lines = text.split("\n")
    tokens = _md.parse(text)

    first_idx = next(
        (i for i, tok in enumerate(tokens) if tok.level == 0 and tok.type.endswith("_open")),
        None,
    )
    if first_idx is None:
        return None, text

    first = tokens[first_idx]
    if first.type == "heading_open":
        is_prompt = first.tag in _PROMPT_HEADING_TAGS
    elif first.type == "paragraph_open":
        inline = tokens[first_idx + 1].content if first_idx + 1 < len(tokens) else ""
        is_prompt = _looks_printed(inline)
    else:
        is_prompt = False

    if not is_prompt or first.map is None:
        return None, text

    start, end = first.map
    prompt = "\n".join(lines[start:end]).strip()
    answer = "\n".join(lines[end:]).strip()
    return (prompt or None), answer
