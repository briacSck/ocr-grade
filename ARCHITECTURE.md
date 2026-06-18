# Architecture

`pipeline.run_batch` orchestrates the stages below sequentially (one page at a
time — no thread pool); `cli.py` is a thin Rich UI on top. The OCR backend and
the header-OCR seam are dependency-injected, so the whole flow runs offline in
tests.

```
   scans/*.pdf
       │
       ▼
 ┌──────────────┐   discover + validate (sha256, page/size limits) → manifest.json
 │  Ingestion   │
 └──────┬───────┘
        ▼
 ┌──────────────┐   rasterize (PyMuPDF) → page PNG; deskew / denoise / contrast
 │  Preprocess  │
 └──────┬───────┘
        ▼
 ┌──────────────┐   black out header_box + regex hits; identity → LOCAL sidecar
 │  Redaction   │   (a cheap header-only OCR pass finds the identity to mask)
 └──────┬───────┘
        │ masked page PNG  ─────────────────────────────────────┐
        ▼                                                        │ original
 ┌──────────────┐   content-addressed cache → Mistral OCR        │ (unmasked)
 │  Mistral OCR │   → markdown (never re-billed for same bytes)  │ scan page
 │   + Cache    │                                                │
 └──────┬───────┘                                                │
        ▼                                                        │
 ┌──────────────┐   normalize markdown; split printed prompt     │
 │ Postprocess  │   from handwritten answer                      │
 └──────┬───────┘                                                │
        ▼                                                        ▼
 ┌────────────────────────────────────────────────────────────────┐
 │ PDF Assembler — interleave scan + transcript (markdown-it →     │
 │ HTML → fitz.Story), compress (pikepdf), 95 MB size guard        │
 └───────────────────────────────┬────────────────────────────────┘
                                 ▼
                  out/{course}_{exam}_{sid}.pdf  +  out/run_report.md
```

## Module responsibilities

| Module | Responsibility |
| --- | --- |
| `cli.py` | Typer entrypoint (`run`, `dry-run`, `purge`, `version`); loads `Settings`, drives the Rich progress bar + live cost. No orchestration logic. |
| `pipeline.py` | The orchestrator: `run_batch`, `estimate` (dry-run), `purge_batch`. Wires every stage; dependency-injectable backend + header OCR. |
| `config.py` | Typed `Settings` (pydantic-settings) from `config.yaml` + `OCR_GRADE__*` env overrides; `MISTRAL_API_KEY` read only from its own env var. |
| `ingestion.py` | Discover + validate input PDFs (corrupt, low native DPI, Mistral page/size limits); write `manifest.json`. |
| `preprocess.py` | Rasterize pages to PNG (PyMuPDF, no Poppler) + toggleable deskew/denoise/contrast. |
| `redaction.py` | Local identity masking (header box + regex), via a cheap stubbable `HeaderOCR` seam; writes a local-only identity sidecar. |
| `ocr/base.py` | `OCRBackend` Protocol + `OCRResult`/`OCRBlock`/`PageMeta` types. |
| `ocr/mistral.py` | The only concrete backend: masked page → Mistral `/v1/ocr`, retries 429/5xx, prices each call. |
| `ocr/cache.py` | Content-addressed OCR cache keyed by masked-image bytes + backend + fingerprint; accumulates cost/hit/miss. |
| `postprocess.py` | Normalize markdown; split printed prompt from handwritten answer via token line-maps. |
| `pdf_assembler.py` | Interleave original scan + transcript page (markdown-it → HTML → `fitz.Story`), compress, enforce the 95 MB ceiling. |
| `reporting.py` | Write `out/run_report.md` (model, pages, failures, cost, wall time). Called by `pipeline.run_batch`. |
| `utils.py` | Small shared helpers. |

## Repo layout

```
ocr-grade/
├── pyproject.toml
├── README.md / ARCHITECTURE.md / OPERATIONS.md
├── config.example.yaml
├── src/ocr_grade/
│   ├── cli.py            # typer entrypoint: run, dry-run, purge, version
│   ├── pipeline.py       # batch orchestration (run_batch / estimate / purge_batch)
│   ├── config.py         # pydantic-settings: yaml + env config
│   ├── ingestion.py      # discover + validate input PDFs
│   ├── preprocess.py     # rasterize (PyMuPDF) + deskew/denoise/contrast
│   ├── redaction.py      # local header masking + identity sidecar
│   ├── ocr/
│   │   ├── base.py       # OCRBackend Protocol + OCRResult types
│   │   ├── mistral.py    # the only concrete OCR backend
│   │   └── cache.py      # content-addressed OCR result cache
│   ├── postprocess.py    # markdown cleanup + prompt/answer split
│   ├── pdf_assembler.py  # interleave scan+transcript, compress, size-guard
│   ├── reporting.py      # out/run_report.md writer
│   └── utils.py
├── tests/
│   ├── fixtures/synthetic/   # synthetic only — no real student data, ever
│   └── test_*.py
└── docs/
    ├── mistral-setup.md
    ├── data-policy.md
    └── runbook.md
```

## Extension points

- **Swap in a second OCR backend:** implement the `ocr.base.OCRBackend` Protocol
  (`name`, a read-only `cache_fingerprint` property, and `transcribe(image_path,
  page_meta) -> OCRResult`) and return it from `pipeline._build_backend`. Nothing
  in ingestion/preprocess/redaction/postprocess/pdf_assembler needs to change —
  the cache keys on `cache_fingerprint`, so a new backend's results stay
  separate.
- **New masking rule:** add a regex to `redaction.regex_patterns`, or set a fixed
  `redaction.header_box` per course preset — no code change for the common case.
  For richer logic (e.g. a learned detector), extend `redaction.mask` and/or the
  `HeaderOCR` seam.
