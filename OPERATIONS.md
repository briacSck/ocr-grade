# Operations

> Stub — fleshed out in Prompt 10 (documentation polish). Section headers
> below match what a second operator will need.

## Install

TODO: `uv sync --dev`, Python 3.11 via `.python-version`.

**Known native-dependency caveat (Windows dev machines):** `pdf2image` needs
the Poppler binaries on PATH, and `weasyprint` needs the Pango/GDK native
libraries. Neither ships via pip. Document the exact install steps here once
Prompt 3 (ingestion/preprocess) and Prompt 8 (pdf_assembler) actually exercise
them.

## Configure

TODO: `config.yaml` from `config.example.yaml`, `MISTRAL_API_KEY` env var
(see `docs/mistral-setup.md`).

## Run a batch

TODO: `ocr-grade dry-run --input ...` then `ocr-grade run --input ... --output ... --course ...`.

## Troubleshoot

TODO.

## Purge

TODO: `ocr-grade purge --batch <sha>`.

## Rotate API key

TODO: see `docs/mistral-setup.md`.
