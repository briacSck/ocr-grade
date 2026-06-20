"""Assemble the final interleaved manuscript + transcript PDF.

For each exam page, the deliverable interleaves the **original scan** (unmasked —
the grader works locally and needs to see the handwriting) with a generated
**transcript page** rendered from the cleaned markdown. The output is named by
the real student ID (local-only, no hashing) and kept under a 95 MB ceiling so
it uploads cleanly to Gradescope.

Markdown is rendered to HTML with markdown-it-py and laid out to PDF with
`fitz.Story` (PyMuPDF) — self-contained, no native libraries (WeasyPrint, which
the original plan named, needs GTK/Pango/cairo natives that aren't installable
on Windows). The same PyMuPDF handles the original scans and the interleave;
pikepdf does the compression pass.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import fitz  # PyMuPDF
import pikepdf
from markdown_it import MarkdownIt
from pydantic import BaseModel

from .ingestion import ExamFile

MAX_OUTPUT_BYTES = 95 * 1024 * 1024
DOWNSAMPLE_DPI = 150
# A Berkeley-style student ID is a 6-10 digit run; used to pick the SID out of
# the sidecar's identity strings (which also include names).
SID_RE = re.compile(r"\d{6,10}")

_md = MarkdownIt()

_CSS = """
body { font-family: sans-serif; color: #111; }
.hdr { font-size: 9pt; color: #555; border-bottom: 1px solid #999;
       padding-bottom: 4px; margin-bottom: 12px; }
.prompt { font-size: 10pt; color: #333; background: #f2f2f2;
          padding: 6px 8px; margin-bottom: 12px; }
.answer { font-size: 12pt; line-height: 1.4; }
"""


class PageTranscript(BaseModel):
    """One page's split transcript (output of `postprocess.split_prompt_and_answer`)."""

    page_number: int  # 1-based; indexes into the original PDF
    prompt: str | None = None
    answer: str = ""


def _safe(name: str) -> str:
    """Make a filename component: whitespace -> '_', drop other unsafe chars."""
    name = re.sub(r"\s+", "_", name.strip())
    return re.sub(r"[^A-Za-z0-9._-]", "", name)


def _resolve_student_id(explicit: str | None, sidecars: list[Path] | None) -> str:
    """Pick the student ID: explicit arg, else the SID-shaped sidecar string."""
    if explicit:
        return explicit
    strings: list[str] = []
    for sidecar in sidecars or []:
        try:
            data = json.loads(Path(sidecar).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        strings.extend(data.get("identity_strings", []))
    for s in strings:
        match = SID_RE.search(s)
        if match:
            return match.group(0)
    return strings[0] if strings else "unknown"


def _transcript_html(course: str, exam_name: str, t: PageTranscript) -> str:
    header = f"{course} — {exam_name} · Page {t.page_number}"
    prompt_html = f'<div class="prompt">{_md.render(t.prompt)}</div>' if t.prompt else ""
    answer_html = f'<div class="answer">{_md.render(t.answer)}</div>'
    return f'<div class="hdr">{header}</div>{prompt_html}{answer_html}'


def _render_transcript_pages(out_doc: fitz.Document, html: str) -> None:
    """Lay out one transcript's HTML into PDF page(s) appended to ``out_doc``."""
    story = fitz.Story(html=html, user_css=_CSS)
    buf = io.BytesIO()
    writer = fitz.DocumentWriter(buf)
    rect = fitz.paper_rect("letter")
    where = rect + (36, 36, -36, -36)
    more = 1
    while more:
        dev = writer.begin_page(rect)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
    with fitz.open("pdf", buf.getvalue()) as tmp:
        out_doc.insert_pdf(tmp)


def _assemble(
    exam: ExamFile,
    transcripts: list[PageTranscript],
    course: str,
    exam_name: str,
    *,
    scan_dpi: int | None,
    scan_rotation: int = 0,
) -> bytes:
    """Build the interleaved PDF bytes (original scan page, then transcript page).

    ``scan_rotation`` is the clockwise rotation the pipeline applied to normalize
    the page to upright; it is folded into the embedded scan's ``/Rotate`` so the
    grader sees the manuscript right-side up next to the transcript.
    """
    out = fitz.open()
    with fitz.open(exam.path) as src:
        for t in transcripts:
            idx = t.page_number - 1
            page_src = src[idx]
            if scan_rotation:
                page_src.set_rotation((page_src.rotation + scan_rotation) % 360)
            if scan_dpi is None:
                out.insert_pdf(src, from_page=idx, to_page=idx)
            else:
                pix = page_src.get_pixmap(dpi=scan_dpi)
                page = out.new_page(width=pix.width, height=pix.height)
                page.insert_image(page.rect, stream=pix.tobytes("jpg"))
            _render_transcript_pages(out, _transcript_html(course, exam_name, t))
    out.set_metadata({})
    data: bytes = out.tobytes()
    out.close()
    return data


def _compress(data: bytes) -> bytes:
    """Recompress streams/objects with pikepdf."""
    with pikepdf.open(io.BytesIO(data)) as pdf:
        buf = io.BytesIO()
        pdf.save(
            buf,
            compress_streams=True,
            recompress_flate=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
        )
        return buf.getvalue()


def build_interleaved(
    exam: ExamFile,
    transcripts: list[PageTranscript],
    out_path: str | Path,
    *,
    student_id: str | None = None,
    identity_sidecars: list[Path] | None = None,
    exam_name: str | None = None,
    course: str | None = None,
    scan_rotation: int = 0,
    max_bytes: int = MAX_OUTPUT_BYTES,
) -> list[Path]:
    """Write the interleaved manuscript+transcript PDF for one exam.

    ``out_path`` is the output directory; the filename
    ``{course}_{exam}_{student_id}.pdf`` is derived here so the size guard can add
    consistent ``_part1`` / ``_part2`` suffixes. Returns the written path(s).

    Size guard: try lossless scans, then 150-DPI downsampled scans, then split the
    pages into two halves — each step is compressed with pikepdf before the
    ``max_bytes`` check.
    """
    out_dir = Path(out_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    course = course or exam.course or "UNKNOWN"
    exam_name = exam_name or exam.path.stem
    resolved_id = _resolve_student_id(student_id, identity_sidecars)
    base = _safe(f"{course}_{exam_name}_{resolved_id}")

    # 1) lossless scans, then 2) downsampled scans.
    for scan_dpi in (None, DOWNSAMPLE_DPI):
        data = _compress(
            _assemble(
                exam, transcripts, course, exam_name, scan_dpi=scan_dpi, scan_rotation=scan_rotation
            )
        )
        if len(data) <= max_bytes:
            target = out_dir / f"{base}.pdf"
            target.write_bytes(data)
            return [target]

    # 3) still too large -> split into two parts (downsampled).
    mid = (len(transcripts) + 1) // 2
    halves = [transcripts[:mid], transcripts[mid:]]
    written: list[Path] = []
    for i, half in enumerate(halves, start=1):
        if not half:
            continue
        data = _compress(
            _assemble(
                exam, half, course, exam_name, scan_dpi=DOWNSAMPLE_DPI, scan_rotation=scan_rotation
            )
        )
        target = out_dir / f"{base}_part{i}.pdf"
        target.write_bytes(data)
        written.append(target)
    return written
