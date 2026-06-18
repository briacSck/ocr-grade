# ocr-grade

A local-first CLI that turns scanned handwritten exam PDFs into Gradescope-ready
interleaved PDFs (each scan page followed by its **Mistral OCR** transcription,
with the printed prompt and the handwritten answer split apart).

Student identity is masked **locally** before any page reaches Mistral; the
extracted names/SIDs stay in a gitignored cache and are never re-sent. See
`docs/data-policy.md`.

## Quickstart (≈30 seconds)

```bash
uv sync --dev                       # install (Python 3.11, pinned via .python-version)
export MISTRAL_API_KEY="…"          # your key — see docs/mistral-setup.md
cp config.example.yaml config.yaml  # then edit input/output/course/redaction
uv run ocr-grade dry-run --config config.yaml   # OCR page 1 only; prints cost + time estimate
uv run ocr-grade run --config config.yaml        # full batch → out/*.pdf + out/run_report.md
```

> On a corporate network whose root CA intercepts HTTPS, prefix `uv` network
> commands with `UV_SYSTEM_CERTS=true` (e.g. `UV_SYSTEM_CERTS=true uv sync --dev`).

## Sample command

```bash
# Override config fields from the command line:
uv run ocr-grade run \
  --config config.yaml \
  --input ./scans \
  --output ./out \
  --course PE101
```

Outputs land in `output_dir` as `{course}_{exam}_{student_id}.pdf` (real student
ID from the local identity sidecar), plus `run_report.md` (pages, failures, total
Mistral cost, wall time, model).

## Commands

| Command | What it does |
| --- | --- |
| `ocr-grade run` | Full pipeline over every valid exam in `input_dir`. |
| `ocr-grade dry-run` | Transcribe page 1 of the first exam; print estimated batch cost + projected time. |
| `ocr-grade purge --batch <sha>` | Delete cached OCR results + intermediate artifacts for one exam. |
| `ocr-grade version` | Print the installed version. |

## Environment variables

| Variable | Purpose |
| --- | --- |
| `MISTRAL_API_KEY` | **Required.** API key, read only from the env (never `config.yaml`). |
| `OCR_GRADE__<FIELD>__<NESTED>` | Override any config field, e.g. `OCR_GRADE__MISTRAL__MODEL=mistral-ocr-2512`, `OCR_GRADE__DPI=250`. |
| `UV_SYSTEM_CERTS=true` | Trust the OS cert store (needed behind an intercepting corporate proxy). |

## Web UI (optional)

A single-user, password-protected upload page is also available for running
batches from a browser instead of the terminal:

```bash
OCR_GRADE_WEB_USER=me OCR_GRADE_WEB_PASSWORD=secret \
  uv run uvicorn ocr_grade.web.app:app --port 8000
```

It reuses the same `config.yaml` and `MISTRAL_API_KEY`. See `docs/deploy.md` for
hosting it (Render / Fly.io / a small VPS).

See `ARCHITECTURE.md` for how it fits together, `OPERATIONS.md` for running a real
batch, and `docs/runbook.md` for the per-cycle grading checklist.
