# Architecture

```
                ┌──────────────┐
   scans/*.pdf  │   Ingestion  │
 ──────────────▶│   + Validate │
                └──────┬───────┘
                       ▼
                ┌──────────────┐    per-page images
                │ Preprocess   │───────────────────┐
                │ (deskew,     │                   │
                │  denoise,    │                   │
                │  mask ID)    │                   │
                └──────┬───────┘                   │
                       ▼                            │
                ┌──────────────┐                    │
                │ Mistral OCR  │  inline bytes      │
                │  + Cache     │  returns markdown  │
                └──────┬───────┘                    │
                       ▼                            │
                ┌──────────────┐                    │
                │ Postprocess  │  markdown-aware    │
                │  (cleanup,   │  prompt/answer     │
                │   split)     │  split             │
                └──────┬───────┘                    │
                       ▼                            ▼
                ┌──────────────────────────────────────┐
                │ PDF Assembler (interleave + compress)│
                └──────────────┬───────────────────────┘
                               ▼
                        out/*.pdf  +  run_report.md
```

## Repo layout

```
ocr-grade/
├── pyproject.toml
├── README.md
├── ARCHITECTURE.md
├── OPERATIONS.md
├── config.example.yaml
├── src/ocr_grade/
│   ├── __init__.py
│   ├── cli.py            # typer entrypoint: run, dry-run, purge, version
│   ├── config.py          # pydantic-settings: yaml + env config
│   ├── ingestion.py        # discover + validate input PDFs
│   ├── preprocess.py       # rasterize (pdf2image) + deskew/denoise/contrast
│   ├── redaction.py        # local header masking + identity sidecar
│   ├── ocr/
│   │   ├── base.py        # OCRBackend Protocol + OCRResult (cheap future-proofing)
│   │   ├── mistral.py     # the only concrete OCR backend
│   │   └── cache.py       # content-addressed OCR result cache
│   ├── postprocess.py      # markdown cleanup + prompt/answer split
│   ├── pdf_assembler.py    # interleave scan+transcript, compress, size-guard
│   ├── reporting.py        # out/run_report.md writer
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

- **New OCR backend:** implement `ocr.base.OCRBackend` and point `cli.py` at it.
  Mistral is the only backend today; the Protocol exists so a swap doesn't
  require touching ingestion/preprocess/postprocess/pdf_assembler.
- **New masking rule:** add a regex pattern to the redaction config, or a new
  fixed header bounding box per course preset — no code change needed for the
  common case.
