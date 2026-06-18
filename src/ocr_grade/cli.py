"""Typer CLI entrypoint for ocr-grade.

The pipeline (ingestion -> preprocess -> mask -> mistral OCR -> postprocess
-> pdf assembly) is wired up in Prompt 9; for now each command is a no-op
that confirms its arguments parsed correctly.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from ocr_grade import __version__

app = typer.Typer(
    help="Turn scanned handwritten exam PDFs into Gradescope-ready interleaved transcripts."
)
console = Console()


@app.command()
def run(
    input: Path = typer.Option(..., "--input", help="Folder of scanned exam PDFs."),
    output: Path = typer.Option(..., "--output", help="Folder to write interleaved PDFs to."),
    course: str = typer.Option(..., "--course", help="Course preset name (e.g. PE101)."),
) -> None:
    """Run the full pipeline over a batch of scanned exams."""
    console.print(
        f"[yellow]TODO:[/yellow] run not yet implemented "
        f"(input={input}, output={output}, course={course})"
    )


@app.command(name="dry-run")
def dry_run(
    input: Path = typer.Option(..., "--input", help="Folder of scanned exam PDFs."),
) -> None:
    """Process page 1 of the first exam and estimate cost/time for the batch."""
    console.print(f"[yellow]TODO:[/yellow] dry-run not yet implemented (input={input})")


@app.command()
def purge(
    batch: str = typer.Option(..., "--batch", help="Batch/exam sha to purge cache+artifacts for."),
) -> None:
    """Delete cache entries and intermediate artifacts for one exam batch."""
    console.print(f"[yellow]TODO:[/yellow] purge not yet implemented (batch={batch})")


@app.command()
def version() -> None:
    """Print the installed ocr-grade version."""
    console.print(__version__)


if __name__ == "__main__":
    app()
