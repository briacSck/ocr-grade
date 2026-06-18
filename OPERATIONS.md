# Operations

How a second operator installs, configures, runs, and maintains `ocr-grade`.
For the exact per-grading-cycle checklist, see `docs/runbook.md`.

## Install

```bash
uv sync --dev    # Python 3.11 is pinned via .python-version; uv fetches it
```

No system packages are required. Rasterization and PDF layout both use
**PyMuPDF**, which bundles its own renderer — there is **no Poppler, GTK, Pango,
or cairo dependency** to install. (An earlier design used WeasyPrint for the
transcript pages; it was dropped precisely because those native libs are not
installable on Windows.)

**Behind a corporate proxy that intercepts HTTPS:** prefix network `uv` commands
with `UV_SYSTEM_CERTS=true` (or export it once), so `uv` trusts the OS cert
store:

```bash
UV_SYSTEM_CERTS=true uv sync --dev
```

## Configure

1. Copy the example and edit it:

   ```bash
   cp config.example.yaml config.yaml
   ```

2. Set the key paths and the course preset:
   - `input_dir` — folder of scanned exam PDFs (one PDF per student).
   - `output_dir` — where interleaved PDFs + `run_report.md` are written.
   - `cache_dir` — local scratch (originals, page PNGs, masked pages, identity
     sidecars, OCR cache). Gitignored; keep it on controlled storage.
   - `course_preset` — used in output filenames (e.g. `PE101`).
   - `redaction.header_box` / `redaction.regex_patterns` — what gets masked
     locally before OCR. **Tune these for your exam template and spot-check.**
   - `mistral.model` — pin a dated revision for reproducible runs
     (see `docs/mistral-setup.md`).

3. Provide the API key via the environment (never in `config.yaml`):

   ```bash
   export MISTRAL_API_KEY="…"
   ```

   See `docs/mistral-setup.md` for account + key creation and rotation.

Any field can be overridden per run with an env var
`OCR_GRADE__<FIELD>__<NESTED_FIELD>` or with `run` flags (`--input`, `--output`,
`--course`).

## Run a batch

Always estimate first:

```bash
uv run ocr-grade dry-run --config config.yaml
```

This transcribes **page 1 of the first exam only** and prints total pages,
estimated cost, and projected wall time. If that looks right:

```bash
uv run ocr-grade run --config config.yaml
```

A Rich progress bar shows pages done and a live running cost. On completion it
prints a summary and writes `output_dir/run_report.md` (model, pages processed,
failures table, total Mistral cost, wall time, output files). `run` exits with a
non-zero status if any page or exam failed, so it is safe to chain in scripts.

## Troubleshoot

| Symptom | Likely cause / fix |
| --- | --- |
| `No valid exams found in <dir>` | `input_dir` wrong/empty, or every PDF was rejected (corrupt, too low native DPI, or over Mistral's page/size limits). Check the per-exam status; re-scan offending files. |
| `invalid peer certificate: UnknownIssuer` during `uv …` | Intercepting corporate CA — re-run with `UV_SYSTEM_CERTS=true`. |
| Auth/401 from Mistral | `MISTRAL_API_KEY` not set/exported in this shell, or revoked. Re-export; rotate if needed. |
| Identity not masked / leaked into transcript | `redaction.header_box` / `regex_patterns` don't match this template. Fix config, **purge the batch** (cached OCR was run on the unmasked-as-intended image), and re-run. |
| Output PDF unexpectedly large | Drop `dpi` (300 → 250). The assembler already enforces a 95 MB ceiling by compressing, then downsampling scans to 150 DPI, then splitting into `_part1`/`_part2`. |
| Re-running re-bills pages you already did | It shouldn't — the OCR cache is content-addressed on the masked image. If you changed the model or masking, that's a new cache key and a legitimate re-bill. |
| Failures listed in `run_report.md` | Each row names the exam/page and reason; the batch continues past failures so good exams still produce PDFs. Fix the cause and re-run (cached pages are reused). |

## Purge

To delete the cached OCR results and intermediate artifacts for one exam (e.g.
after fixing masking, or to remove sensitive scratch when grading is done):

```bash
uv run ocr-grade purge --batch <sha> --config config.yaml
```

`<sha>` is the exam's sha256 (the subdirectory name under `cache_dir`). This
removes `cache_dir/<sha>/` and the content-addressed `cache_dir/ocr/<key>.json`
entries that those pages produced. It does **not** delete already-written output
PDFs.

## Rotate API key

1. Generate a new key in the Mistral console; export it as `MISTRAL_API_KEY`.
2. Revoke the old key in the console.
3. Do this on a quarterly cadence, and **immediately** if a key is ever leaked or
   committed. Full procedure: `docs/mistral-setup.md`.
