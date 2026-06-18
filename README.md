# ocr-grade

A local-first CLI that turns scanned handwritten exam PDFs into Gradescope-ready
interleaved PDFs (scan page, then its Mistral OCR transcription), using
**Mistral OCR 3** for handwriting-capable, layout-preserving transcription.

See `ARCHITECTURE.md` for how it fits together and `OPERATIONS.md` for running
a real batch.

## Quickstart

```bash
uv sync --dev
export MISTRAL_API_KEY=...   # see docs/mistral-setup.md
uv run ocr-grade --help
```

Status: project skeleton only — `run`, `dry-run`, and `purge` are not yet
implemented (see `CHANGELOG.md`).
