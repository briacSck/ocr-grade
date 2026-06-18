# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- Single-user web UI (`ocr_grade.web`, FastAPI): an HTTP Basic-authenticated
  upload page where `POST /batches` accepts a folder zip of scanned exam PDFs,
  runs the same `pipeline.run_batch` in a background task, and exposes a
  per-batch status page plus download links (per-PDF and a "download all" zip)
  for the interleaved transcripts. Reuses the same `MISTRAL_API_KEY`; batch state
  is in-memory and nothing persists beyond the per-batch working directory (no
  database, no multi-tenant features). Added a `Dockerfile` and `docs/deploy.md`
  (Render / Fly.io / VPS, and why serverless platforms like Vercel don't fit).
  New deps: `fastapi`, `uvicorn[standard]`, `python-multipart`.
- Project skeleton bootstrapped: `src/ocr_grade/` package layout, Typer CLI
  (`run`, `dry-run`, `purge`, `version` — all no-ops except `version`), ruff +
  mypy config, pre-commit hooks (ruff, real-data/secret guards), CI workflow,
  doc stubs.
- Phase 0 Mistral OCR sample sanity-check script (`scripts/sample_sanity_check.py`),
  validated against 80 anonymized sample pages.
- Typed `Settings` model (`ocr_grade.config`) loaded from `config.yaml` with
  env var overrides (`OCR_GRADE__<FIELD>__<NESTED_FIELD>`); `MISTRAL_API_KEY`
  is always read from its own plain env var and never from yaml.
- Ingestion + preprocess pipeline front-end: `ingestion.discover()` validates
  input PDFs (corrupt, low native DPI, Mistral page/size limits) and writes a
  `manifest.json`; `preprocess.rasterize()` renders pages to cached PNGs via
  PyMuPDF (no Poppler needed) and `preprocess.clean()` does toggleable
  deskew/denoise/CLAHE-contrast. Replaced `pdf2image` with `pymupdf`.
- Local identity masking (`redaction.mask()`): blacks out a configured header
  box and, via a cheap header-only OCR pass (the stubbable `HeaderOCR` seam),
  masks the header band when configured identity regexes match. Extracted
  identity strings and masked regions are written to a LOCAL-ONLY sidecar under
  the cache dir and never re-sent to Mistral. Added `truststore` dependency.
- OCR backend seam + cache (`ocr.base`, `ocr.cache`): `OCRBackend` Protocol with
  `OCRResult`/`OCRBlock`/`PageMeta` types, and a content-addressed `OCRCache`
  keyed by image bytes + backend name + model/params fingerprint that stores
  results as JSON and accumulates per-batch cost/hit/miss stats so identical
  pages are never re-billed.
- Mistral OCR backend (`ocr.mistral.MistralOCRBackend`): sends a masked page
  inline as a base64 `image_url` data URI, parses the returned markdown into
  heading/paragraph/list blocks (markdown-it-py), retries 429/5xx with tenacity
  (max 5 attempts, honoring `Retry-After`), and prices each call from
  `mistral_price_per_page`. Filled in `docs/mistral-setup.md` and
  `docs/data-policy.md`.
- Markdown post-processing (`postprocess`): `clean_text()` normalizes whitespace
  and blank runs while preserving markdown structure, and
  `split_prompt_and_answer()` re-parses the cleaned markdown (markdown-it-py) to
  split each page into the printed prompt (a leading h1/h2/h3 heading or a
  printed-looking paragraph) and the handwritten answer, slicing losslessly via
  token line-maps.
- Final PDF assembler (`pdf_assembler.build_interleaved`): interleaves each
  original (unmasked) scan page with a transcript page rendered from the cleaned
  markdown (markdown-it-py → HTML → `fitz.Story`), names the file
  `{course}_{exam}_{student_id}.pdf` from the real student ID in the identity
  sidecar, and enforces a 95 MB ceiling with a pikepdf compression pass that
  falls back to 150-DPI scan downsampling and then a part-1/part-2 split.
- End-to-end pipeline + CLI (`pipeline`, `cli`): `run` wires
  ingestion → preprocess → mask → Mistral OCR (cached) → postprocess → assembler
  sequentially per page with a Rich progress bar and a live cost total, writing
  one interleaved PDF per exam plus `out/run_report.md` (pages, failures, total
  cost, wall time, model). `dry-run` transcribes page 1 of the first exam and
  projects batch cost/time; `purge --batch <sha>` deletes an exam's cached OCR
  entries and intermediate artifacts. The OCR backend and header-OCR seam are
  dependency-injected so the whole flow is tested offline.

### Documentation
- Handoff documentation pass: rewrote `README.md` (30-second quickstart, sample
  command, env-var table), `OPERATIONS.md` (install/configure/run/troubleshoot/
  purge/rotate-key), and `ARCHITECTURE.md` (refreshed diagram, per-module
  responsibility table, extension points incl. `pipeline.py`); added
  `docs/runbook.md` with the exact per-grading-cycle checklist.

### Changed
- Moved the `run_report.md` writer into `reporting.py` (`write_run_report`) so the
  module matches its documented responsibility; `pipeline.run_batch` imports it.
- `OCRBackend.cache_fingerprint` is now a read-only Protocol property (it is a
  computed `@property` on the Mistral backend).
- Render transcript pages with PyMuPDF's self-contained `fitz.Story` engine
  instead of WeasyPrint, which requires GTK/Pango/cairo native libraries that
  are not installable on Windows. Dropped the `weasyprint` dependency.
