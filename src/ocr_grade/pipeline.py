"""End-to-end batch orchestration (no UI).

Wires the stages — ingestion -> preprocess -> mask -> Mistral OCR (cached) ->
postprocess -> assembler — into `run_batch`, plus `estimate` (dry-run) and
`purge_batch`. The OCR backend and header-OCR seam are dependency-injected so the
whole flow is testable offline; `cli.py` adds the Rich progress UI on top.

The image that reaches the main OCR pass is always the **masked** page (identity
blacked out locally first); only the local sidecar keeps the extracted identity.
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import cv2

from .config import Settings
from .ingestion import ExamFile, ValidationStatus, discover
from .ocr.base import OCRBackend, PageMeta
from .ocr.cache import OCRCache, _cache_key
from .ocr.mistral import MistralOCRBackend
from .pdf_assembler import PageTranscript, build_interleaved
from .postprocess import clean_text, split_prompt_and_answer
from .preprocess import PageImage, clean, rasterize
from .redaction import HeaderOCR, mask


@dataclass
class Failure:
    exam: str
    page: int | None
    reason: str


@dataclass
class RunReport:
    model: str
    pages_processed: int
    failures: list[Failure] = field(default_factory=list)
    total_cost_usd: float = 0.0
    wall_seconds: float = 0.0
    outputs: list[Path] = field(default_factory=list)


@dataclass
class DryRunEstimate:
    model: str
    total_pages: int
    sample_seconds: float
    estimated_cost_usd: float
    projected_wall_seconds: float


# Callback fired after each processed page: (pages_done, running_cost_usd).
OnPage = Callable[[int, float], None]


def _build_backend(settings: Settings) -> OCRBackend:
    """Construct the real OCR backend (monkeypatch seam for tests)."""
    return MistralOCRBackend(settings)


def _ok_exams(exams: list[ExamFile]) -> list[ExamFile]:
    return [e for e in exams if e.status == ValidationStatus.OK]


def _process_page(
    exam: ExamFile,
    pimg: PageImage,
    settings: Settings,
    backend: OCRBackend,
    cache: OCRCache,
    header_ocr: HeaderOCR | None,
) -> tuple[PageTranscript, Path | None]:
    """Clean -> mask -> OCR (masked) -> split one page into a transcript."""
    cleaned_img = clean(pimg.image, settings.preprocess_steps)
    masked = mask(
        PageImage(page_number=pimg.page_number, image=cleaned_img, path=pimg.path),
        settings,
        header_ocr,
    )

    assert pimg.path is not None  # rasterize always sets a path
    masked_path = pimg.path.with_name(f"{pimg.path.stem}.masked.png")
    cv2.imwrite(str(masked_path), masked.image)

    meta = PageMeta(page_number=pimg.page_number, exam_sha=exam.sha256, course=exam.course)
    result = cache.get_or_call(backend, masked_path, meta)

    prompt, answer = split_prompt_and_answer(clean_text(result))
    transcript = PageTranscript(page_number=pimg.page_number, prompt=prompt, answer=answer)
    return transcript, masked.sidecar_path


def _process_exam(
    exam: ExamFile,
    settings: Settings,
    backend: OCRBackend,
    cache: OCRCache,
    header_ocr: HeaderOCR | None,
    failures: list[Failure],
    on_page: OnPage | None,
    pages_done: int,
) -> tuple[list[Path], int]:
    """Process every page of one exam and assemble its interleaved PDF."""
    try:
        pages = rasterize(exam, settings.dpi, settings.cache_dir)
    except Exception as exc:  # noqa: BLE001 - report and skip the whole exam
        failures.append(Failure(exam=exam.path.name, page=None, reason=str(exc)))
        return [], pages_done

    transcripts: list[PageTranscript] = []
    sidecars: list[Path] = []
    for pimg in pages:
        try:
            transcript, sidecar = _process_page(exam, pimg, settings, backend, cache, header_ocr)
            transcripts.append(transcript)
            if sidecar is not None:
                sidecars.append(sidecar)
        except Exception as exc:  # noqa: BLE001 - record and continue
            failures.append(Failure(exam=exam.path.name, page=pimg.page_number, reason=str(exc)))
        finally:
            pages_done += 1
            if on_page is not None:
                on_page(pages_done, cache.total_cost_usd)

    if not transcripts:
        return [], pages_done

    outputs = build_interleaved(
        exam,
        transcripts,
        settings.output_dir,
        identity_sidecars=sidecars,
        course=settings.course_preset,
    )
    return outputs, pages_done


def run_batch(
    settings: Settings,
    *,
    backend: OCRBackend | None = None,
    header_ocr: HeaderOCR | None = None,
    on_page: OnPage | None = None,
) -> RunReport:
    """Run the full pipeline over every valid exam in ``settings.input_dir``."""
    backend = backend or _build_backend(settings)
    cache = OCRCache(settings.cache_dir)
    exams = discover(settings.input_dir, cache_dir=settings.cache_dir)

    failures: list[Failure] = [
        Failure(exam=e.path.name, page=None, reason=f"skipped ({e.status}): {e.message}")
        for e in exams
        if e.status != ValidationStatus.OK
    ]

    outputs: list[Path] = []
    pages_done = 0
    start = time.perf_counter()
    for exam in _ok_exams(exams):
        exam_outputs, pages_done = _process_exam(
            exam, settings, backend, cache, header_ocr, failures, on_page, pages_done
        )
        outputs.extend(exam_outputs)
    wall_seconds = time.perf_counter() - start

    report = RunReport(
        model=settings.mistral.model,
        pages_processed=cache.hits + cache.misses,
        failures=failures,
        total_cost_usd=cache.total_cost_usd,
        wall_seconds=wall_seconds,
        outputs=outputs,
    )
    write_run_report(report, settings.output_dir)
    return report


def estimate(
    settings: Settings,
    *,
    backend: OCRBackend | None = None,
    header_ocr: HeaderOCR | None = None,
) -> DryRunEstimate:
    """Process page 1 of the first valid exam and extrapolate cost/time."""
    backend = backend or _build_backend(settings)
    cache = OCRCache(settings.cache_dir)
    exams = discover(settings.input_dir, cache_dir=settings.cache_dir)
    ok = _ok_exams(exams)
    if not ok:
        raise RuntimeError(f"No valid exams found in {settings.input_dir}.")

    total_pages = sum(e.page_count for e in ok)
    first = ok[0]
    pages = rasterize(first, settings.dpi, settings.cache_dir)

    start = time.perf_counter()
    _process_page(first, pages[0], settings, backend, cache, header_ocr)
    sample_seconds = time.perf_counter() - start

    return DryRunEstimate(
        model=settings.mistral.model,
        total_pages=total_pages,
        sample_seconds=sample_seconds,
        estimated_cost_usd=settings.mistral_price_per_page * total_pages,
        projected_wall_seconds=sample_seconds * total_pages,
    )


def purge_batch(
    settings: Settings,
    sha: str,
    *,
    backend: OCRBackend | None = None,
) -> list[Path]:
    """Delete cache entries and intermediate artifacts for one exam's sha."""
    cache_dir = Path(settings.cache_dir)
    exam_dir = cache_dir / sha
    deleted: list[Path] = []

    if exam_dir.exists():
        backend = backend or _build_backend(settings)
        for masked_png in exam_dir.glob("*.masked.png"):
            key = _cache_key(masked_png.read_bytes(), backend)
            entry = cache_dir / "ocr" / f"{key}.json"
            if entry.exists():
                entry.unlink()
                deleted.append(entry)
        shutil.rmtree(exam_dir)
        deleted.append(exam_dir)

    return deleted


def write_run_report(report: RunReport, out_dir: str | Path) -> Path:
    """Write ``run_report.md`` summarizing the batch; return its path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "run_report.md"

    lines = [
        "# Run report",
        "",
        f"- **Model:** {report.model}",
        f"- **Pages processed:** {report.pages_processed}",
        f"- **Total Mistral cost (main OCR):** ${report.total_cost_usd:.4f}",
        f"- **Wall time:** {report.wall_seconds:.1f}s",
        f"- **Failures:** {len(report.failures)}",
        "",
        "_Header-detection OCR crops are billed separately and not included in the cost above._",
        "",
        "## Outputs",
        "",
    ]
    lines += [f"- `{p.name}`" for p in report.outputs] or ["- (none)"]

    lines += ["", "## Failures", ""]
    if report.failures:
        lines.append("| Exam | Page | Reason |")
        lines.append("| --- | --- | --- |")
        lines += [
            f"| {f.exam} | {f.page if f.page is not None else '-'} | {f.reason} |"
            for f in report.failures
        ]
    else:
        lines.append("None.")

    path.write_text("\n".join(lines) + "\n")
    return path
