# OCR Grading Tool — PRD, Development Plan & Claude Code Prompts

**Project owner:** Briac
**Client / primary user:** Prof. Crystal Chang (UC Berkeley — PE101, P156, third smaller course)
**Document version:** v0.4 — June 2026 (minimal / Textract-only / single AWS account)
**Status:** Pre-development; awaiting ~15 anonymized sample scripts.

**Scope sizing:** ~400 papers/year × ~20 pages = ~8,000 pages, run in ~3 batches/semester, 2–3 operators. This plan is intentionally scoped to that workload — no second backend, no async path, no parallelism, no cost cap. Add complexity only when reality demands it.

---

## 0. Executive Summary

A local-first CLI that ingests scanned handwritten exam PDFs, transcribes each page using **AWS Textract** (handwriting + `LAYOUT` blocks for prompt/answer structure), and produces an **interleaved PDF** — scan page followed by its transcription — compatible with Gradescope's section-assignment workflow. Identifying information is stripped locally before any Textract call.

Phase 1 success = one working CLI that turns Crystal's scanned PDF batch into Gradescope-ready interleaved PDFs (<100 MB each) within an evening run on real samples.

---

# PART A — Product Requirements Document (PRD)

## A.1 Problem Statement

Crystal grades essay-based handwritten exams (~230 students/semester across 3 courses; ~16–22 pages/student). Roughly **1 in 5 scripts is hard to read**, slowing grading inside Gradescope. A prior GSI (Ray) built a basic Python OCR pipeline producing interleaved manuscript+transcription PDFs that proved useful but was not maintained. We need to rebuild and harden that workflow with AWS Textract, basic privacy controls, and clear operability.

## A.2 Goals & Non-Goals

### Goals (Phase 1 — MVP)
1. Accept a scanned exam PDF (one student or a batch) as input.
2. Produce an **interleaved PDF**: page 1 = scan, page 2 = transcription of page 1, etc.
3. Preserve exam structure (prompt at top, answer below) so Gradescope section assignment still works.
4. Keep output PDFs **under 100 MB** (Gradescope limit).
5. Strip names/IDs from images before any Textract call (so handwritten text isn't sent to a cloud OCR); reattach on the final local PDF using the original student ID.
6. Run unattended in an evening on a single laptop.
7. Ship documentation a second engineer could pick up cold.

### Non-Goals
- Automated grading or rubric scoring.
- Second OCR backend / A/B harness.
- Async Textract path with S3 staging.
- Multi-threaded batch execution.
- Cost cap enforcement (negligible at this scale).
- Citation verification, multi-tenant web app, LMS integrations beyond Gradescope-compatible PDFs.

### Stretch (Phase 2+)
- Lightweight private web upload UI (single-user auth) hosted on Crystal's AWS account.
- Confidence highlighting (low-confidence tokens flagged in red on the transcription page).
- Async S3 path — only if real scans actually exceed Textract sync limits.

## A.3 Users & Use Cases

| User | Need | Frequency |
|---|---|---|
| Crystal (primary) | Convert scans -> interleaved PDFs before grading window | 3x per semester per course |
| Briac (dev/operator) | Run, monitor, debug pipeline | As needed |

**Primary use case:** Crystal finishes scanning -> drops PDFs into an input folder -> runs one command -> receives interleaved PDFs ready to upload to Gradescope.

## A.4 Functional Requirements

### F1. Ingestion
- F1.1 Accept multi-page PDFs (one PDF per student OR one PDF containing many students with a separator convention).
- F1.2 Accept folder of PDFs as batch input.
- F1.3 Validate: not corrupt, reasonable DPI (>=200), file size, page count.
- F1.4 Reject pages exceeding Textract sync limits (10 MB image, 5000x5000 px) with a clear error pointing the operator to lower the DPI in config. We will not implement the async path in Phase 1.

### F2. Preprocessing
- F2.1 Rasterize each PDF page to image (configurable DPI, default 300; lower to 250 if file size becomes a problem).
- F2.2 Deskew, denoise, contrast-normalize (all individually toggleable).
- F2.3 Detect & redact identifying regions (student name, SID) via a fixed header bounding box from a course template OR a regex pass after a first cheap header-only OCR. Redacted copies go to Textract; originals stay local.
- F2.4 Persist a per-page manifest (page_id <-> original_image <-> redacted_image <-> identity_metadata).

### F3. OCR (AWS Textract)
- F3.1 **Single backend: AWS Textract** via `boto3`, called from the operator's own AWS account.
- F3.2 Per page, call `analyze_document` with `FeatureTypes=["LAYOUT"]` (no `FORMS` — we don't need key-value pairs for essays).
- F3.3 Sync path only. Each call sends the redacted image as raw `Bytes`.
- F3.4 Retry with tenacity exponential backoff (max 5 attempts) on `ThrottlingException`, `ProvisionedThroughputExceededException`, `InternalServerError`.
- F3.5 Parse the BLOCK tree (PAGE -> LAYOUT blocks -> LINE -> WORD) into a structured result with per-line bbox, per-word confidence, and LAYOUT block types (TITLE, SECTION_HEADER, TEXT) preserved.
- F3.6 Caching: identical (image hash, feature flags) -> cached result, no re-call. This is what makes re-runs cheap.
- F3.7 Per-page cost & latency logged from a configurable price-per-page constant.

### F4. Postprocessing
- F4.1 Light cleanup: collapse spurious line breaks, normalize whitespace, preserve paragraph structure.
- F4.2 Use Textract LAYOUT block types to detect printed prompt (`TITLE`/`SECTION_HEADER`) vs. handwritten answer (`TEXT`); keep prompt at top of the transcription page.
- F4.3 Optional confidence highlighting (Phase 2).

### F5. PDF Assembly
- F5.1 Build interleaved PDF: [scan_page_1, transcript_page_1, scan_page_2, transcript_page_2, ...].
- F5.2 Reattach the original student name/SID on the cover page of the final local PDF (the redacted version was only for Textract; the final local PDF is for Crystal's own use in Gradescope).
- F5.3 Compress: target <=95 MB; if exceeded, downsample scan images and split into part-1 / part-2 PDFs with consistent naming.
- F5.4 Output filename convention: `{course}_{exam}_{student_id}.pdf` using the real student ID from the identity sidecar. Student IDs are roster data already shared with Gradescope and Canvas, so no anonymization is needed in the filename.

### F6. CLI & Config
- F6.1 Single command: `ocr-grade run --input ./scans --output ./out --course PE101`.
- F6.2 Config file (`config.yaml`) for AWS profile/region, DPI, redaction template, course presets, Textract price constants.
- F6.3 Dry-run mode (process page 1 of first exam, show estimated total cost and time for the batch).

### F7. Observability
- F7.1 Per-batch run log: pages processed, failures, total Textract cost, wall time.
- F7.2 Per-page artifact directory retained for debugging (toggleable).
- F7.3 Summary report (`out/run_report.md`) generated next to the output PDFs.

## A.5 Non-Functional Requirements

| Area | Requirement |
|---|---|
| Performance | A semester batch (~2,500–4,600 pages) finishes overnight on a single laptop running sequential Textract calls. |
| Cost | Tracked per page; expected total ~$120–$400/year all-in. No hard cap. |
| Privacy | No name/SID leaves the local machine. All Textract calls receive redacted images only. AWS region pinned to a US region. |
| Reliability | Resumable: re-running on the same input skips already-processed pages via cache. Textract retries on throttling/5xx. |
| Portability | macOS and Linux; Python 3.11+; single `uv sync` or `pip install -e .`. |
| Documentation | README + ARCHITECTURE.md + OPERATIONS.md + docs/aws-setup.md + docs/data-policy.md + CHANGELOG. |

## A.6 Privacy, Compliance, Data Handling

- **Local-first**: scans never leave the operator's machine in unredacted form.
- **Redaction**: header-region masking + name/SID regex pass before any Textract call.
- **Vendor**: AWS Textract under standard AWS service terms (no customer-input training when called from the operator's own account). Region pinned to a US region. Policy excerpt + link captured in `docs/data-policy.md`.
- **AWS account model (Phase 1):** everything runs in Briac's personal AWS account. This keeps the dev loop fast and avoids needing scheduled co-working time with Crystal. If/when the pilot succeeds, Briac sets up an identical IAM user + policy in Crystal's AWS account so she can run it independently — same code, same config schema, just different `AWS_PROFILE`. IAM user is least-privilege: `textract:AnalyzeDocument` + `textract:DetectDocumentText`.
- **No S3 bucket needed** in Phase 1 (sync path only) — eliminates a whole class of data-residency concerns.
- **At rest (local)**: all artifacts in a single working directory the operator controls; no implicit cloud sync.
- **Deletion**: `ocr-grade purge --batch <id>` removes all intermediate artifacts; final PDFs are the only retained output.

## A.7 Success Metrics (Pilot)

- >=90% of pages produce a transcription a human can read alongside the scan without losing time vs. reading the scan alone.
- On the ~20% "hard handwriting" bucket, transcription is rated "helpful" by Crystal on >=60% of pages.
- Zero leakage incidents (no name/SID transmitted to Textract).
- Crystal can run a batch end-to-end with the documentation alone.

## A.8 Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Textract handwriting quality on cursive / messy scripts | Manual review of 15 samples in Phase 0 before committing to Textract; tune preprocessing (denoise, contrast). If unacceptable, add a second backend later — keep the adapter interface in place. |
| Redaction misses an ID written elsewhere | Combine fixed-region masking + regex + manual review of first batch. |
| Gradescope upload limit (100 MB) | Compression + automatic split + filename convention. |
| Page exceeds Textract sync limits | Clear error message + config hint to lower DPI; add async path in Phase 2 only if it actually happens. |
| AWS Textract pricing/policy changes | Price constants in config, not code; policy snapshot in `docs/data-policy.md`. |
| Briac unavailable mid-semester | Documentation + clean repo + scheduled progress updates. AWS setup is documented as a self-contained checklist so Crystal can replicate it in her own account without Briac. |

## A.9 Open Questions (carried from call notes)

1. Final scan DPI and file characteristics — answered after sample receipt.
2. Can name/SID always be auto-stripped? — confirm after redaction pass on samples.
3. Final form factor: CLI only, or CLI + small private web UI? — decide after MVP.
4. When to migrate to Crystal's AWS account — after the MVP works on Briac's account and the pilot is green.

---

# PART B — Development Plan

## B.1 Phasing

### Phase 0 — Discovery (Days 0–3, blocked on samples)
- Receive 15 anonymized samples from Crystal.
- Catalogue: page count distribution, handwriting difficulty buckets, header layout.
- Run Textract on all 15 samples manually (one-off script) and eyeball results with Crystal. **Decision gate:** is Textract good enough? If yes, proceed. If no, revisit backend choice before writing more code.
- **Exit:** sample report committed to repo.

### Phase 1 — MVP CLI (Weeks 1–3)
- Implement ingestion, preprocessing, redaction, Textract backend (sync only), postprocessing with LAYOUT-aware split, PDF assembly, CLI, caching, docs.
- **Exit:** Crystal runs the CLI on her own machine on a real (non-sample) past exam batch.

### Phase 2 — Hardening (Weeks 4–5)
- Confidence highlighting using Textract per-word confidence.
- First end-to-end pilot on a current semester exam.
- **Exit:** pilot retrospective with Crystal; go/no-go on web UI.

### Phase 2.5 — AWS account migration (after pilot, before scaling to all 3 courses)
- Briac walks Crystal through `docs/aws-setup.md` in her own account (IAM user, policy, region pin, credentials).
- Briac switches `AWS_PROFILE` and runs the same pipeline against the same scans to verify identical output.
- **Exit:** Crystal owns the AWS account; Briac is an IAM operator there.

### Phase 3 (optional) — Private Web UI (Weeks 6–8)
- Single-user authenticated upload page; backend reuses the same pipeline.
- Hosted on Crystal's AWS account.
- **Exit:** Crystal uses the web UI for a full grading cycle.

## B.2 Architecture (MVP)

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
                │  redact ID)  │                   │
                └──────┬───────┘                   │
                       ▼                            │
                ┌──────────────┐                    │
                │  Textract    │  sync only         │
                │  + Cache     │  LAYOUT feature    │
                └──────┬───────┘                    │
                       ▼                            │
                ┌──────────────┐                    │
                │ Postprocess  │  uses Textract     │
                │  (cleanup,   │  LAYOUT blocks for │
                │   layout)    │  prompt/answer     │
                └──────┬───────┘                    │
                       ▼                            ▼
                ┌──────────────────────────────────────┐
                │ PDF Assembler (interleave + compress)│
                └──────────────┬───────────────────────┘
                               ▼
                        out/*.pdf  +  run_report.md
```

**Repo layout:**
```
ocr-grade/
├── pyproject.toml
├── README.md
├── ARCHITECTURE.md
├── OPERATIONS.md
├── config.example.yaml
├── src/ocr_grade/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── ingestion.py
│   ├── preprocess.py
│   ├── redaction.py
│   ├── ocr/
│   │   ├── base.py        # OCRBackend Protocol (future-proofs cheaply)
│   │   ├── textract.py    # only concrete backend
│   │   └── cache.py
│   ├── postprocess.py
│   ├── pdf_assembler.py
│   ├── reporting.py
│   └── utils.py
├── tests/
│   ├── fixtures/   # synthetic only — no real student data
│   └── test_*.py
└── docs/
    ├── aws-setup.md
    ├── data-policy.md
    └── runbook.md
```

## B.3 Tech Stack

- **Language:** Python 3.11+
- **Package mgr:** `uv`
- **PDF I/O:** `pypdf`, `pdf2image` (Poppler), `pikepdf` for compression
- **Imaging:** `Pillow`, `opencv-python`
- **OCR:** **AWS Textract via `boto3`** (sole backend)
- **CLI:** `typer`
- **Config:** `pydantic-settings` + YAML
- **Caching:** content-addressed local store (`.cache/`)
- **Testing:** `pytest`, `pytest-snapshot`, `moto[textract]` for AWS mocking
- **Lint/format:** `ruff`, `mypy`
- **CI:** GitHub Actions (lint, tests on PR)

## B.4 Milestones & Deliverables

| Milestone | Deliverable | Target |
|---|---|---|
| M0 — Samples received + Textract sanity-check | Sample report in `docs/samples.md` with verdict | After Crystal sends |
| M1 — Skeleton repo | Repo + CI + CLI scaffold | Week 1 |
| M2 — Textract happy path | One PDF in -> interleaved PDF out | Week 2 |
| M3 — Redaction + cache + docs | Privacy guarantees met; resumable runs; docs | Week 3 |
| M4 — Real batch run | Crystal runs on a past exam batch | Week 4 |
| M5 — Pilot run | Live semester pilot complete | End of Week 5 |
| M6 — Decision gate | Web UI go/no-go | Week 6 |

## B.5 Working Agreements

- Weekly written update to Crystal (Friday) — scope, progress, blockers, AWS costs.
- Every PR has a description that another engineer could read cold.
- No real student data committed to git, ever (pre-commit hook enforces this).
- AWS access keys never committed; only profiles or env vars; rotated quarterly.
- Phase 1 runs on Briac's personal AWS account; switch to Crystal's account only after the pilot is green.

---

# PART C — Claude Code Prompt Set

Use these prompts in order inside Claude Code at the repo root. Each is self-contained; paste it, let the agent work, review the diff, commit, then move on.

> **Conventions:** small reviewable PRs; add or update tests; never commit real student data; update `README.md` and `CHANGELOG.md` as part of the change.

### Prompt 0 — Phase 0 sample sanity-check (one-off, before building anything)
```
Write `scripts/sample_sanity_check.py` — a one-off Phase 0 script (no package
structure yet). It:

- Takes a folder of PDF samples and an AWS profile name.
- For each page of each PDF: rasterizes at 300 DPI (pdf2image), then calls
  Textract `analyze_document` with FeatureTypes=["LAYOUT"] via boto3.
- Writes `samples_report.md` with, per page: a thumbnail of the scan, the
  reconstructed Textract text, the detected LAYOUT block types, and the average
  per-word confidence.
- Prints total Textract cost using a configurable price-per-page constant.

Goal: Crystal and Briac eyeball this report together and decide whether Textract
quality is good enough on real handwriting before building the full app.

Commit as `chore(phase0): textract sanity-check script`.
```

### Prompt 1 — Bootstrap the repository
```
Set up a new Python project called `ocr-grade`:

1. Initialize a `uv`-managed Python 3.11 project with `pyproject.toml`.
2. Dependencies: typer, pydantic, pydantic-settings, pyyaml, pillow, opencv-python,
   pdf2image, pypdf, pikepdf, rich, tenacity, boto3.
   Dev deps: pytest, pytest-cov, pytest-snapshot, ruff, mypy, pre-commit,
   moto[textract].
3. Package layout under `src/ocr_grade/`: cli, config, ingestion, preprocess,
   redaction, ocr/{base,cache,textract}, postprocess, pdf_assembler, reporting,
   utils.
4. Configure ruff + mypy. Add `.pre-commit-config.yaml` with:
   - ruff
   - hook rejecting any staged file under `tests/fixtures/real/` or any *.pdf
     outside `tests/fixtures/synthetic/`
   - hook scanning staged files for AWS access key patterns
     (AKIA[0-9A-Z]{16}) and blocking the commit.
5. GitHub Actions workflow `.github/workflows/ci.yml` running lint + tests on PR.
6. Files: README.md, ARCHITECTURE.md (copy the architecture diagram and repo
   layout from the project plan), OPERATIONS.md (stub), CHANGELOG.md,
   config.example.yaml, docs/aws-setup.md (stub), docs/data-policy.md (stub).
7. Typer CLI entrypoint `ocr-grade --help` with subcommands `run`, `dry-run`,
   `purge`, `version` — all no-ops printing TODO.
8. Verify with `uv run pytest` and `uv run ocr-grade --help`.

Commit as `chore: bootstrap project skeleton`.
```

### Prompt 2 — Config & input model
```
Implement `src/ocr_grade/config.py`:

- Pydantic `Settings` model loaded from `config.yaml` + env vars.
- Fields:
    input_dir, output_dir, cache_dir,
    dpi (default 300),
    course_preset (str),
    redaction: { header_box: [x,y,w,h] | None, regex_patterns: list[str] },
    aws: { profile: str | None,
           region: str = "us-east-1",
           access_key_id: SecretStr | None,
           secret_access_key: SecretStr | None },
    textract_price_per_page (float, configurable),
    preprocess_steps: { deskew: bool, denoise: bool, contrast: bool }.
- A `load_settings(path)` helper.
- Update `config.example.yaml` with documented defaults and a commented AWS block.
- Tests: load example file, override via env var
  (e.g. OCR_GRADE__AWS__REGION), validation errors on bad values.

Commit as `feat(config): typed settings with yaml + env loading`.
```

### Prompt 3 — Ingestion & preprocessing
```
Implement `ingestion.py` and `preprocess.py`:

- `ingestion.discover(input_dir) -> list[ExamFile]` returning records with path,
  page_count, sha256, detected course (from filename pattern), validation status.
- Reject corrupt PDFs and PDFs whose rasterized DPI looks below ~150.
- Reject pages that, after rasterization, would exceed Textract sync limits
  (10 MB image or 5000x5000 px) with a clear error pointing at the `dpi` config.
- `preprocess.rasterize(exam_file, dpi) -> list[PageImage]` using pdf2image.
- `preprocess.clean(image) -> image` applying deskew (Hough), denoise, adaptive
  contrast. Each step toggleable via settings.preprocess_steps.
- Write artifacts to `cache_dir/<exam_sha>/page_<n>.png`.
- Tests with synthetic PDFs generated on the fly (reportlab) — no real student data.

Commit as `feat(ingest): pdf -> cleaned page images with manifest`.
```

### Prompt 4 — Redaction
```
Implement `redaction.py`:

- `redact(page_image, settings) -> RedactedPage`:
  1. Mask the configured header bounding box (if any) with a solid rectangle.
  2. Run a cheap header-only OCR pass (Textract `detect_document_text` on a small
     crop is fine; abstract behind a `HeaderOCR` interface stubbable in tests),
     then apply configured regex patterns
     (e.g. r"SID[:\s]*\d{7,10}", r"Name[:\s]*[A-Z][a-z]+ [A-Z][a-z]+")
     and mask matching regions.
  3. Return: redacted image + sidecar JSON with masked regions + extracted
     identity strings — kept LOCAL ONLY, never sent in full to Textract.
- Tests: synthetic page with a fake "Name: John Doe / SID: 12345678" header gets
  the region masked and identity captured in the sidecar.

Commit as `feat(redaction): local header masking + identity sidecar`.
```

### Prompt 5 — OCR adapter interface + cache
```
Implement `ocr/base.py` and `ocr/cache.py`:

- `class OCRBackend(Protocol)`:
    name: str
    def transcribe(self, image_path: Path, page_meta: PageMeta) -> OCRResult
- `OCRResult`: text, lines (each with text + bbox + per-word confidence + LAYOUT
  block type), raw_response, cost_usd, latency_ms.
- `cache.py`: content-addressed cache keyed by sha256(image_bytes) + backend.name
  + serialized feature flags. Stores OCRResult as JSON.
- A `get_or_call(backend, image_path, meta)` helper.
- Tests with a fake in-memory backend covering cache hits/misses and cost
  accumulation.

(We keep the Protocol even though Textract is currently the only backend —
30 lines that make a future swap trivial.)

Commit as `feat(ocr): backend protocol + content-addressed cache`.
```

### Prompt 6 — AWS Textract backend (sole backend, sync only)
```
Implement `ocr/textract.py`:

- `boto3` Textract client. Region + credentials from settings (AWS profile OR
  explicit access key + secret key as SecretStr). Never hardcoded.
- Single sync path: `analyze_document` with FeatureTypes=["LAYOUT"], passing the
  redacted image as raw `Bytes`. No FORMS, no async, no S3.
- Wrap calls with tenacity exponential backoff (max 5 attempts) on
  ThrottlingException, ProvisionedThroughputExceededException,
  InternalServerError.
- Parse the BLOCK tree (PAGE -> LAYOUT_* -> LINE -> WORD) into OCRResult with
  per-line bbox, per-word confidence, and LAYOUT block types (TITLE,
  SECTION_HEADER, TEXT) preserved on each line.
- Per-call cost = settings.textract_price_per_page (do not hardcode).
- Unit tests use `moto` to mock Textract (happy path, throttling retry,
  permanent failure). Integration test gated behind env var AWS_PROFILE — skipped
  otherwise.
- Fill in `docs/aws-setup.md`:
    * Create an IAM user `ocr-grade-operator`.
    * Attach this least-privilege policy JSON verbatim:
        {
          "Version": "2012-10-17",
          "Statement": [
            { "Effect": "Allow",
              "Action": [
                "textract:AnalyzeDocument",
                "textract:DetectDocumentText"
              ],
              "Resource": "*" }
          ]
        }
    * Configure local `~/.aws/credentials` or env vars; pin the region.
    * No S3 bucket needed in Phase 1.
- Fill in `docs/data-policy.md` with the current AWS service terms excerpt and
  link stating Textract input is not used to train AWS models, plus the chosen
  US region and the IAM policy summary.

Commit as `feat(ocr): AWS Textract sync backend`.
```

### Prompt 7 — Postprocessing
```
Implement `postprocess.py`:

- `clean_text(ocr_result) -> CleanedPage`: collapse spurious line breaks,
  normalize whitespace, preserve paragraph boundaries inferred from line bbox
  gaps.
- `split_prompt_and_answer(cleaned) -> (prompt_block, answer_block)`:
  use Textract LAYOUT block types — TITLE / SECTION_HEADER lines at the top of
  the page form the prompt; TEXT lines below form the answer. If the page has no
  TITLE/SECTION_HEADER blocks, return whole page as answer with prompt_block=None.
- Tests on synthetic OCRResults.

Commit as `feat(postprocess): cleanup + LAYOUT-aware prompt/answer split`.
```

### Prompt 8 — PDF assembler
```
Implement `pdf_assembler.py`:

- `build_interleaved(exam, transcripts, out_path)`: alternates scan page (from
  the original PDF, NOT redacted) and a generated transcript page. Transcript
  page layout: course/exam header, page number, prompt block (if any) at top in
  a smaller font, then the answer in monospace-ish body font.
- Compression pass with pikepdf; if final size > 95 MB, downsample images and
  retry; if still > 95 MB, split into part-1 / part-2 with consistent filename
  suffixes.
- Filename: `{course}_{exam}_{student_id}.pdf` using the real student ID from the
  identity sidecar (no hashing — student IDs are roster data already shared with
  Gradescope/Canvas).
- Tests: golden-file comparison on a tiny synthetic exam.

Commit as `feat(pdf): interleaved manuscript+transcript assembler with size guard`.
```

### Prompt 9 — Wire the CLI end-to-end
```
Wire `cli.py run` to execute the full pipeline:

ingestion -> preprocess -> redact -> textract (cached) -> postprocess
-> pdf_assembler.

- Sequential per page (no ThreadPoolExecutor — overkill at our scale).
- Rich progress bar over total pages.
- Print a running cost total as we go.
- `dry-run`: process page 1 of the first exam only, print estimated total cost
  and projected wall time for the full batch.
- `purge --batch <sha>`: delete cache entries and intermediate artifacts for
  one exam.
- Emit `out/run_report.md`: pages processed, failures, total Textract cost,
  wall time.

Commit as `feat(cli): end-to-end run with dry-run and purge`.
```

### Prompt 10 — Documentation polish
```
Update docs for handoff:

- README.md: 30-second quickstart + sample command.
- OPERATIONS.md: install, configure, AWS setup pointer, run a batch, troubleshoot,
  purge, rotate AWS keys.
- ARCHITECTURE.md: refresh diagram, list module responsibilities, list extension
  points (swap in a second backend by implementing OCRBackend, new redaction rule).
- docs/aws-setup.md: finalize IAM policy (textract:AnalyzeDocument +
  textract:DetectDocumentText only), region pin, credential storage, key
  rotation cadence.
- docs/data-policy.md: AWS Textract data-policy excerpt + link, region,
  redaction guarantees, deletion procedure.
- docs/runbook.md: exact steps Crystal runs each grading cycle.

Commit as `docs: handoff-grade documentation`.
```

### Prompt 11 — (Optional Phase 2) Confidence highlighting
```
Highlight low-confidence tokens in red on the transcript page, driven by Textract
per-word confidence (configurable threshold, default 0.6). Add a `--no-highlight`
CLI flag. Update golden tests.

Commit as `feat(pdf): low-confidence token highlighting`.
```

### Prompt 12 — (Optional Phase 3) Minimal private web UI
```
Add `web/` subpackage:

- FastAPI app with one authenticated upload page (single user via HTTP basic auth
  or a signed magic link from settings).
- Endpoint POST /batches accepts a folder zip, runs the same pipeline in a
  background task, exposes a status page and a download link for the interleaved
  PDFs.
- Dockerfile + docs/deploy-aws.md describing deployment on a single EC2 or
  Fargate task inside Crystal's AWS account, reusing the same IAM role that
  already has Textract permissions.
- No multi-tenant features. No persistence beyond the working directory.

Commit as `feat(web): single-user private upload UI`.
```

---

## Appendix — Quickstart for Briac

```bash
# Phase 0 (before building the app)
python scripts/sample_sanity_check.py ./samples --aws-profile ocr-grade-dev
# eyeball samples_report.md with Crystal; decide go/no-go on Textract.

# Then, repo setup
git init ocr-grade && cd ocr-grade
# paste Prompt 1 into Claude Code; review; commit. Then Prompt 2, etc.

# AWS one-time (per docs/aws-setup.md):
#   - create IAM user ocr-grade-operator with the 2-action least-privilege policy
#   - configure AWS_PROFILE locally
#   - no S3 bucket needed

# Typical run, once built
ocr-grade dry-run --input ./scans
ocr-grade run --input ./scans --output ./out --course PE101
```

## Appendix — Items to confirm with Crystal before Phase 1 close

1. AWS Textract data-policy excerpt reviewed and accepted (Briac's account; same policy when we migrate to hers).
2. Header bounding box for redaction (per course template).
3. Form factor after MVP: CLI only vs. CLI + private web UI.
4. Timing for the Phase 2.5 AWS migration to Crystal's account.
