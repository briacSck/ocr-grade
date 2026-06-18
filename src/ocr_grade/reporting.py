"""Run-level reporting.

Holds the writer for ``out/run_report.md``: pages processed, failures, total
Mistral cost, wall time, and the model name used. `pipeline.run_batch` calls
`write_run_report` at the end of a batch.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .pipeline import RunReport


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
