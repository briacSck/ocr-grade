# Maintainer notes

Developer/architecture reference for `ocr-grade`. End users never need this file —
they use `README.md`. Keep this concise; it replaces the old ARCHITECTURE /
OPERATIONS / CHANGELOG docs.

## What it is

A local-first tool that turns scanned handwritten exam PDFs into Gradescope-ready
**interleaved** PDFs: each scan page followed by its Mistral-OCR transcription
(printed prompt split from handwritten answer). Student identity is masked
**locally** before any page reaches Mistral. There are two front ends over the
same pipeline: a Typer **CLI** and a single-user **web UI** (FastAPI).

## Architecture

`pipeline.run_batch` runs the stages below sequentially, one page at a time. The
OCR backend and the header-OCR seam are dependency-injected, so the whole flow
runs offline in tests.

```
scans/*.pdf
   → Ingestion    discover + validate (sha256, DPI floor, Mistral page/size limits)
   → Preprocess   rasterize (PyMuPDF) → PNG; auto-orient; deskew/denoise/contrast
   → Redaction    detect rotation, black out the identity header band;
                  identity strings → LOCAL-only sidecar (never re-sent)
   → Mistral OCR  masked page → /v1/ocr → markdown (content-addressed cache)
   → Postprocess  normalize markdown; split printed prompt vs handwritten answer
   → PDF Assembler interleave original scan + transcript; compress; 95 MB guard
   → out/{course}_{exam}_{sid}.pdf  +  out/run_report.md
```

| Module | Responsibility |
| --- | --- |
| `cli.py` | Typer entrypoint (`run`, `dry-run`, `purge`, `version`); Rich progress + live cost. Loads `.env`. |
| `pipeline.py` | Orchestrator: `run_batch`, `estimate`, `purge_batch`. Injectable backend + header OCR. |
| `config.py` | Typed `Settings` (pydantic-settings) from `config.yaml` + `OCR_GRADE__*` env. `MISTRAL_API_KEY` read from its own env var. Includes `min_native_dpi` and `redaction.auto_orient`. |
| `ingestion.py` | Discover + validate PDFs (corrupt, low DPI, Mistral limits); write `manifest.json`. |
| `preprocess.py` | Rasterize (PyMuPDF, no Poppler); `rotate_image` + `text_is_horizontal` helpers; deskew/denoise/contrast. |
| `redaction.py` | `detect_orientation` (geometric axis + identity-OCR flip) and `mask` (header-band masking + local identity sidecar) behind the stubbable `HeaderOCR` seam. |
| `ocr/base.py`,`ocr/mistral.py`,`ocr/cache.py` | Backend Protocol + types; the Mistral `/v1/ocr` backend (retries 429/5xx); content-addressed cache keyed on masked-image bytes + model fingerprint. |
| `postprocess.py` | Markdown cleanup; split printed prompt from handwritten answer. |
| `pdf_assembler.py` | Interleave scan + transcript (`markdown-it` → HTML → `fitz.Story`), pikepdf compress, 95 MB size guard, `scan_rotation` baked into embedded scans. |
| `reporting.py` | Write `out/run_report.md`. |
| `web/` | Single-user FastAPI UI (`app`, `batches`, `settings`): authenticated zip upload → `run_batch` in a background task → status page + downloads. Loads `.env`. Thin wrapper, no pipeline logic. |

All text I/O is pinned to `encoding="utf-8"` (Windows defaults to cp1252 and
crashes on math glyphs otherwise).

## Develop

```bash
uv sync --dev            # Python 3.11 pinned via .python-version; uv fetches it
uv run pytest            # full suite (one test makes a real Mistral call if a key is set)
uv run pytest -k "not integration"   # offline suite
uv run ruff check src tests
```

Behind an intercepting corporate proxy, prefix network `uv` commands with
`UV_SYSTEM_CERTS=true`.

## Run

```bash
# CLI
export MISTRAL_API_KEY=...          # or put it in .env
uv run ocr-grade dry-run --config config.yaml     # OCR page 1, estimate cost/time
uv run ocr-grade run     --config config.yaml     # full batch → out/
uv run ocr-grade purge --batch <sha> --config config.yaml

# Web UI (what ships to the end user; .env supplies key + login)
uv run uvicorn ocr_grade.web.app:app --port 8000
```

Config reference: every option is documented inline in `config.example.yaml`.
The shipped `config.yaml` is a ready-to-use copy (course set per-batch in the UI).

## Troubleshoot

| Symptom | Cause / fix |
| --- | --- |
| `No valid exams found` | `input_dir` wrong/empty, or all PDFs rejected (corrupt, below `min_native_dpi`, or over Mistral's 50 MB / 1000-page limits). |
| `invalid peer certificate: UnknownIssuer` during `uv …` | Intercepting corporate CA — re-run with `UV_SYSTEM_CERTS=true`. |
| 401 from Mistral | `MISTRAL_API_KEY` not set in the env / `.env`, or revoked. |
| Identity leaked into a transcript | Masking config doesn't match the template, or `auto_orient` mis-detected. Fix `redaction.*`, **purge** the batch, re-run. |
| Re-running re-bills done pages | Expected only if the model or masking changed (new cache key). |

## OCR quality

Transcription accuracy is bounded by handwriting legibility and scan resolution,
**not** by Mistral plan tier (tiers gate rate/quota, not model quality). Biggest
lever: scan at ~300 DPI. The interleaved original scan is intentionally kept next
to the transcript so the grader cross-checks rather than trusting OCR blindly.

## Privacy invariant

Only the **masked** page (identity blacked out) and one cheap header crop reach
Mistral. Extracted identity strings live only in the gitignored cache sidecars.
Never commit student data; `tests/fixtures/` is synthetic only. See
`docs/data-policy.md`.

## Extension points

- **Second OCR backend:** implement `ocr.base.OCRBackend` (`name`,
  `cache_fingerprint`, `transcribe`) and return it from `pipeline._build_backend`.
  Cache keys on the fingerprint, so results stay separate. No other stage changes.
- **New masking rule:** add a regex to `redaction.regex_patterns` or set a fixed
  `redaction.header_box`; extend `redaction.mask` / the `HeaderOCR` seam for richer logic.

## Version notes

- **v1 (current):** full pipeline (ingestion → preprocess → redaction → Mistral OCR
  + cache → postprocess → interleaved assembler), Typer CLI, single-user web UI.
  Pre-ship hardening: configurable `min_native_dpi`, UTF-8 text I/O, dynamic page
  auto-orientation before masking, `.env`-based config + macOS launch scripts.
