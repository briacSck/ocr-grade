from pathlib import Path

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from typer.testing import CliRunner

from ocr_grade import __version__, pipeline
from ocr_grade.cli import app
from ocr_grade.ocr.base import OCRResult, PageMeta

runner = CliRunner()


def test_help_lists_subcommands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("run", "dry-run", "purge", "version"):
        assert command in result.output


def test_version_command_prints_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


class _FakeBackend:
    name = "fake"
    cache_fingerprint = "fake-model|{}"

    def transcribe(self, image_path: Path, page_meta: PageMeta) -> OCRResult:
        return OCRResult(markdown_text="# Q1\n\nAnswer line.", cost_usd=0.002)


def _write_config(tmp_path: Path) -> Path:
    scans = tmp_path / "scans"
    scans.mkdir()
    c = canvas.Canvas(str(scans / "PE101.pdf"), pagesize=letter)
    c.drawString(72, 720, "Scanned page 1")
    c.showPage()
    c.save()

    config = tmp_path / "config.yaml"
    config.write_text(
        f"input_dir: {scans.as_posix()}\n"
        f"output_dir: {(tmp_path / 'out').as_posix()}\n"
        f"cache_dir: {(tmp_path / 'cache').as_posix()}\n"
        "course_preset: PE101\n"
        "dpi: 150\n"
        "redaction:\n"
        "  regex_patterns:\n"
        "    - 'SID[:\\s]*\\d{7,10}'\n"
        "mistral:\n"
        "  model: mistral-ocr-test\n"
        "preprocess_steps:\n"
        "  deskew: false\n"
        "  denoise: false\n"
        "  contrast: false\n"
    )
    return config


def test_run_command_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "test")
    monkeypatch.setattr(pipeline, "_build_backend", lambda settings: _FakeBackend())
    monkeypatch.setattr(
        "ocr_grade.redaction.MistralHeaderOCR.read_header",
        lambda self, header_png: "SID: 1234567",
    )

    config = _write_config(tmp_path)
    result = runner.invoke(app, ["run", "--config", str(config)])

    assert result.exit_code == 0, result.output
    assert "$0.0020" in result.output
    assert (tmp_path / "out" / "run_report.md").exists()
    assert (tmp_path / "out" / "PE101_PE101_1234567.pdf").exists()
