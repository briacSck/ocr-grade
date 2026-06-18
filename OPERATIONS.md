# Operations

> Stub — fleshed out in Prompt 10 (documentation polish). Section headers
> below match what a second operator will need.

## Install

TODO: `uv sync --dev`, Python 3.11 via `.python-version`.

**Known native-dependency caveat (Windows dev machines):** rasterization uses
`PyMuPDF`, which bundles its own renderer — **no Poppler install is required**.
The remaining native caveat is `weasyprint` (Prompt 8 / `pdf_assembler`), which
needs the Pango/GDK libraries; document its exact install steps here once that
prompt exercises them.

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
