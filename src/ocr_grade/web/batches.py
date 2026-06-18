"""In-memory batch registry and the background job that runs the pipeline.

State lives only in this process (a dict guarded by a lock) and on disk under the
per-batch working directory — there is no database and nothing persists beyond
the working directory, per the single-user design.
"""

from __future__ import annotations

import threading
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from ..config import load_settings
from ..pipeline import run_batch
from .settings import WebSettings

Status = str  # "queued" | "running" | "done" | "failed"


@dataclass
class Batch:
    id: str
    status: Status = "queued"
    pages_done: int = 0
    cost_usd: float = 0.0
    outputs: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    error: str | None = None
    model: str | None = None
    course: str | None = None
    root: Path | None = None  # workdir/<id>

    @property
    def out_dir(self) -> Path:
        assert self.root is not None
        return self.root / "out"


_LOCK = threading.Lock()
BATCHES: dict[str, Batch] = {}


def register(batch: Batch) -> None:
    with _LOCK:
        BATCHES[batch.id] = batch


def get(batch_id: str) -> Batch | None:
    with _LOCK:
        return BATCHES.get(batch_id)


def _update(batch_id: str, **fields: object) -> None:
    with _LOCK:
        batch = BATCHES.get(batch_id)
        if batch is None:
            return
        for key, value in fields.items():
            setattr(batch, key, value)


class UploadError(ValueError):
    """Raised when an uploaded zip is missing PDFs, unsafe, or too large."""


def extract_zip(zip_path: Path, input_dir: Path, max_bytes: int) -> int:
    """Extract ``*.pdf`` members from ``zip_path`` into ``input_dir`` (flattened).

    Flattens to basenames so nested folders and any path-traversal / absolute
    members (zip-slip) cannot escape ``input_dir``. Enforces ``max_bytes`` on the
    total uncompressed size. Returns the number of PDFs extracted.
    """
    input_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    count = 0
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = Path(info.filename).name  # basename only — zip-slip safe
                if not name.lower().endswith(".pdf"):
                    continue
                total += info.file_size
                if total > max_bytes:
                    raise UploadError("Uploaded archive exceeds the size limit.")
                dest = input_dir / name
                with zf.open(info) as src, dest.open("wb") as out:
                    out.write(src.read())
                count += 1
    except zipfile.BadZipFile as exc:
        raise UploadError("Uploaded file is not a valid zip archive.") from exc

    if count == 0:
        raise UploadError("Archive contained no PDF files.")
    return count


def run_job(batch_id: str, web: WebSettings) -> None:
    """Run the full pipeline for one batch; record progress and results in-memory."""
    batch = get(batch_id)
    if batch is None or batch.root is None:
        return

    _update(batch_id, status="running")
    try:
        base = load_settings(web.base_config)
        overrides: dict[str, object] = {
            "input_dir": batch.root / "input",
            "output_dir": batch.root / "out",
            "cache_dir": batch.root / "cache",
        }
        if batch.course:
            overrides["course_preset"] = batch.course
        settings = base.model_copy(update=overrides)

        def on_page(pages_done: int, cost: float) -> None:
            _update(batch_id, pages_done=pages_done, cost_usd=cost)

        report = run_batch(settings, on_page=on_page)
        _update(
            batch_id,
            status="done",
            pages_done=report.pages_processed,
            cost_usd=report.total_cost_usd,
            outputs=[p.name for p in report.outputs],
            failures=[f"{f.exam} (page {f.page}): {f.reason}" for f in report.failures],
            model=report.model,
        )
    except Exception as exc:  # noqa: BLE001 - surface any failure to the status page
        _update(batch_id, status="failed", error=str(exc))
