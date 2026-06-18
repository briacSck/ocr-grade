# Data policy

This tool processes scanned **student exams**, which are sensitive education
records. This page describes what leaves your machine and what does not.

## What stays local (never sent to Mistral)

- **Original scanned PDFs** and the full-resolution rasterized page PNGs under
  the cache directory.
- **Extracted student identity** (names, SIDs). The redaction pass
  (`ocr_grade.redaction`) writes matched identity strings and masked regions to a
  local-only sidecar (`<page>.identity.json`) under the gitignored cache dir.
  These strings are **never** sent back to Mistral.

## What is sent to Mistral

- **The masked page image only.** Before any full page is transcribed, the
  header band (configured `header_box` and/or any region where an identity regex
  matched) is blacked out with a solid rectangle. The masked PNG is sent inline
  as a base64 `image_url` data URI to the `/v1/ocr` endpoint — no upload to
  Mistral's `/files` store and no public URL hosting.
- **One cheap header-only crop**, once per page, for the identity-detection OCR
  pass. This crop is what lets us find and mask the identity; it is sent only for
  that read and the resulting identity strings are kept local (see above).

The masked page → `OCRResult` (markdown + heading/paragraph/list blocks) is the
only transcription output; results are cached locally and keyed by image content
so the same page is never re-sent or re-billed.

## Mistral's handling of submitted data

Data you send to the Mistral API is governed by Mistral's current terms and
privacy policy, and by your account's data-processing settings:

- Privacy Policy: <https://mistral.ai/terms/#privacy-policy>
- Terms of Use / Data Processing: <https://mistral.ai/terms/>
- OCR API docs: <https://docs.mistral.ai/api/endpoint/ocr>

Retention windows and whether submitted content may be used to improve models
depend on your plan and account configuration, and these terms change over time.
**Before processing real student data, verify the current policy and confirm your
account's training/retention settings** (e.g. opt out of training-on-your-data if
your plan offers it, and prefer a plan with a zero/short retention commitment).
When in doubt, treat anything sent to the API as leaving your custody — which is
exactly why identity is masked locally first.

## Operator checklist

- Confirm masking config (`redaction.header_box`, `redaction.regex_patterns`) is
  correct for the exam template **before** a batch run; spot-check masked pages.
- Keep the cache dir (originals, PNGs, identity sidecars) on local/controlled
  storage; it is gitignored and must not be committed or synced to shared drives.
- Delete cache artifacts when a grading run is complete and they are no longer
  needed.
