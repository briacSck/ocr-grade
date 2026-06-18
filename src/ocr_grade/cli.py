"""Typer CLI entrypoint for ocr-grade.

Thin UI layer over `pipeline`: loads `Settings` (config file + optional flag
overrides), drives a Rich progress bar with a live cost total for `run`, and
prints the `dry-run` estimate / `purge` results. All orchestration lives in
`ocr_grade.pipeline`.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

from ocr_grade import __version__, pipeline
from ocr_grade.config import Settings, load_settings
from ocr_grade.ingestion import ValidationStatus, discover

app = typer.Typer(
    help="Turn scanned handwritten exam PDFs into Gradescope-ready interleaved transcripts."
)
console = Console()


def _load(
    config: Path,
    *,
    input: Path | None = None,
    output: Path | None = None,
    course: str | None = None,
) -> Settings:
    """Load settings from ``config``, applying any CLI flag overrides."""
    settings = load_settings(config)
    if input is not None:
        settings.input_dir = input
    if output is not None:
        settings.output_dir = output
    if course is not None:
        settings.course_preset = course
    return settings


@app.command()
def run(
    config: Path = typer.Option(Path("config.yaml"), "--config", help="Path to config.yaml."),
    input: Path | None = typer.Option(None, "--input", help="Override input_dir."),
    output: Path | None = typer.Option(None, "--output", help="Override output_dir."),
    course: str | None = typer.Option(None, "--course", help="Override course_preset."),
) -> None:
    """Run the full pipeline over a batch of scanned exams."""
    settings = _load(config, input=input, output=output, course=course)

    exams = discover(settings.input_dir, cache_dir=settings.cache_dir)
    total_pages = sum(e.page_count for e in exams if e.status == ValidationStatus.OK)
    if total_pages == 0:
        console.print(f"[red]No valid exams found in {settings.input_dir}.[/red]")
        raise typer.Exit(code=1)

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Transcribing  $0.0000", total=total_pages)

        def on_page(pages_done: int, cost: float) -> None:
            progress.update(task, completed=pages_done, description=f"Transcribing  ${cost:.4f}")

        report = pipeline.run_batch(settings, on_page=on_page)

    console.print(
        f"\n[green]Done.[/green] {report.pages_processed} pages, "
        f"{len(report.outputs)} PDF(s), ${report.total_cost_usd:.4f}, "
        f"{report.wall_seconds:.1f}s. "
        f"Report: {settings.output_dir / 'run_report.md'}"
    )
    if report.failures:
        console.print(f"[yellow]{len(report.failures)} failure(s) — see the run report.[/yellow]")
        raise typer.Exit(code=1)


@app.command(name="dry-run")
def dry_run(
    config: Path = typer.Option(Path("config.yaml"), "--config", help="Path to config.yaml."),
    input: Path | None = typer.Option(None, "--input", help="Override input_dir."),
) -> None:
    """Process page 1 of the first exam and estimate cost/time for the batch."""
    settings = _load(config, input=input)
    est = pipeline.estimate(settings)
    console.print(
        f"[bold]Dry run[/bold] (model {est.model})\n"
        f"  Sample page time : {est.sample_seconds:.1f}s\n"
        f"  Total pages      : {est.total_pages}\n"
        f"  Estimated cost   : ${est.estimated_cost_usd:.4f}\n"
        f"  Projected time   : {est.projected_wall_seconds:.0f}s "
        f"(~{est.projected_wall_seconds / 60:.1f} min)"
    )


@app.command()
def purge(
    batch: str = typer.Option(..., "--batch", help="Exam sha to purge cache+artifacts for."),
    config: Path = typer.Option(Path("config.yaml"), "--config", help="Path to config.yaml."),
) -> None:
    """Delete cache entries and intermediate artifacts for one exam batch."""
    settings = _load(config)
    deleted = pipeline.purge_batch(settings, batch)
    if deleted:
        console.print(f"[green]Purged {len(deleted)} item(s)[/green] for {batch}.")
    else:
        console.print(f"Nothing to purge for {batch}.")


@app.command()
def version() -> None:
    """Print the installed ocr-grade version."""
    console.print(__version__)


if __name__ == "__main__":
    app()
