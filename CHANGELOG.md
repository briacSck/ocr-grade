# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
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
