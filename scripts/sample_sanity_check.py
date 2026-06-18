# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mistralai",
#   "pymupdf",
#   "pillow",
#   "python-dotenv",
#   "truststore",
# ]
# ///
"""Phase 0 one-off script: run Mistral OCR over a folder (or single PDF) of
anonymized exam samples and produce a markdown report for human review.

Usage:
    export MISTRAL_API_KEY=...
    uv run scripts/sample_sanity_check.py ./samples
    uv run scripts/sample_sanity_check.py "20 Anonomized Exams.pdf" --max-pages 2

Not part of the ocr-grade package (no package structure exists yet). This
script is throwaway: it exists only to decide, with Crystal, whether Mistral
OCR's handwriting quality is good enough to justify building the full CLI.
"""

from __future__ import annotations

import argparse
import base64
import io
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
import truststore
from dotenv import load_dotenv
from PIL import Image

# Use the OS certificate store (Windows/macOS) instead of certifi's bundle so
# corporate TLS-intercepting proxies/root CAs are trusted for Mistral API calls.
truststore.inject_into_ssl()


@dataclass
class PageResult:
    pdf_name: str
    page_number: int  # 1-indexed within its PDF
    thumbnail_rel_path: str
    markdown: str | None
    error: str | None
    latency_s: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Mistral OCR over sample exam PDFs and build a review report."
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Folder containing PDF samples, or a single PDF file.",
    )
    parser.add_argument(
        "--model",
        default="mistral-ocr-latest",
        help="Mistral OCR model alias (default: mistral-ocr-latest, "
        "currently resolves to mistral-ocr-2512).",
    )
    parser.add_argument("--dpi", type=int, default=300, help="Rasterization DPI (default: 300).")
    parser.add_argument(
        "--price-per-page",
        type=float,
        default=0.001,
        help="USD cost per page used to compute the printed total (default: 0.001).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("samples_report.md"),
        help="Path to write the markdown report (default: samples_report.md).",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Optional cap on total pages processed across all PDFs (for a cheap test run).",
    )
    parser.add_argument(
        "--thumbnail-width",
        type=int,
        default=350,
        help="Thumbnail width in pixels embedded in the report (default: 350).",
    )
    return parser.parse_args()


def discover_pdfs(input_path: Path) -> list[Path]:
    if input_path.is_dir():
        pdfs = sorted(input_path.glob("*.pdf"))
        if not pdfs:
            sys.exit(f"No PDF files found in folder: {input_path}")
        return pdfs
    if input_path.is_file() and input_path.suffix.lower() == ".pdf":
        return [input_path]
    sys.exit(f"Input is neither a folder nor a PDF file: {input_path}")


def rasterize_page(page: fitz.Page, dpi: int) -> bytes:
    pix = page.get_pixmap(dpi=dpi)
    return pix.tobytes("png")


def save_thumbnail(png_bytes: bytes, width: int, thumbnails_dir: Path, filename: str) -> Path:
    image = Image.open(io.BytesIO(png_bytes))
    if image.width > width:
        ratio = width / image.width
        image = image.resize((width, int(image.height * ratio)))
    thumbnails_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = thumbnails_dir / filename
    image.save(thumb_path, format="PNG")
    return thumb_path


def call_mistral_ocr(client, model: str, png_bytes: bytes) -> str:
    encoded = base64.b64encode(png_bytes).decode("ascii")
    response = client.ocr.process(
        model=model,
        document={
            "type": "image_url",
            "image_url": f"data:image/png;base64,{encoded}",
        },
    )
    return response.pages[0].markdown


def write_report(
    output_path: Path,
    results: list[PageResult],
    model: str,
    dpi: int,
    price_per_page: float,
    total_wall_s: float,
) -> None:
    succeeded = [r for r in results if r.error is None]
    failed = [r for r in results if r.error is not None]
    total_cost = len(succeeded) * price_per_page

    lines: list[str] = []
    lines.append("# Mistral OCR sample sanity-check report")
    lines.append("")
    lines.append(f"- Model: `{model}`")
    lines.append(f"- DPI: {dpi}")
    lines.append(f"- Pages processed: {len(results)} ({len(succeeded)} ok, {len(failed)} failed)")
    lines.append(f"- Price per page: ${price_per_page:.4f}")
    lines.append(f"- Total cost (succeeded pages only): ${total_cost:.4f}")
    lines.append(f"- Total wall time: {total_wall_s:.1f}s")
    lines.append("")
    lines.append("---")

    current_pdf = None
    for r in results:
        if r.pdf_name != current_pdf:
            current_pdf = r.pdf_name
            lines.append("")
            lines.append(f"## {current_pdf}")

        lines.append("")
        lines.append(f"### Page {r.page_number}")
        lines.append("")
        lines.append(f"![page {r.page_number} thumbnail]({r.thumbnail_rel_path})")
        lines.append("")
        if r.error is not None:
            lines.append(f"**ERROR ({r.latency_s:.1f}s):** {r.error}")
        else:
            lines.append(f"_latency: {r.latency_s:.1f}s_")
            lines.append("")
            lines.append("```markdown")
            lines.append(r.markdown or "")
            lines.append("```")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    load_dotenv()
    args = parse_args()

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        sys.exit("MISTRAL_API_KEY is not set. Export it before running this script.")

    from mistralai.client import Mistral

    client = Mistral(api_key=api_key)

    pdf_paths = discover_pdfs(args.input)

    output_path = args.output
    thumbnails_dir = output_path.parent / f"{output_path.stem}_thumbnails"

    results: list[PageResult] = []
    pages_processed = 0
    start = time.time()

    for pdf_path in pdf_paths:
        if args.max_pages is not None and pages_processed >= args.max_pages:
            break

        doc = fitz.open(pdf_path)
        try:
            for page_index in range(doc.page_count):
                if args.max_pages is not None and pages_processed >= args.max_pages:
                    break

                page = doc.load_page(page_index)
                png_bytes = rasterize_page(page, args.dpi)
                thumb_filename = f"{pdf_path.stem}_p{page_index + 1:03d}.png"
                thumb_path = save_thumbnail(png_bytes, args.thumbnail_width, thumbnails_dir, thumb_filename)
                thumbnail_rel_path = os.path.relpath(thumb_path, output_path.parent).replace(os.sep, "/")

                page_start = time.time()
                error: str | None = None
                markdown: str | None = None
                try:
                    markdown = call_mistral_ocr(client, args.model, png_bytes)
                except Exception as exc:  # noqa: BLE001 - sanity script, keep going on any failure
                    error = f"{type(exc).__name__}: {exc}"
                latency = time.time() - page_start

                results.append(
                    PageResult(
                        pdf_name=pdf_path.name,
                        page_number=page_index + 1,
                        thumbnail_rel_path=thumbnail_rel_path,
                        markdown=markdown,
                        error=error,
                        latency_s=latency,
                    )
                )
                pages_processed += 1
                status = "ok" if error is None else "FAILED"
                print(f"[{pages_processed}] {pdf_path.name} page {page_index + 1}: {status} ({latency:.1f}s)")
        finally:
            doc.close()

    total_wall_s = time.time() - start

    write_report(args.output, results, args.model, args.dpi, args.price_per_page, total_wall_s)

    succeeded = sum(1 for r in results if r.error is None)
    failed = len(results) - succeeded
    total_cost = succeeded * args.price_per_page
    print()
    print(f"Wrote {args.output} ({len(results)} pages: {succeeded} ok, {failed} failed)")
    print(f"Total cost: ${total_cost:.4f} ({succeeded} pages x ${args.price_per_page:.4f}/page)")
    print(f"Total wall time: {total_wall_s:.1f}s")


if __name__ == "__main__":
    main()
