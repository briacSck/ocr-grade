# Grading-cycle runbook

The exact steps to run for each exam you grade. Assumes the one-time setup in
`OPERATIONS.md` (Install + Configure) and `docs/mistral-setup.md` is done and a
working `config.yaml` exists. Run every command from the repo root.

## Before you start (once per machine / session)

1. Confirm the key is set in this shell:

   ```bash
   echo "$MISTRAL_API_KEY"   # should print your key, not blank
   ```

   If blank: `export MISTRAL_API_KEY="…"` (PowerShell: `$env:MISTRAL_API_KEY = "…"`).
2. Confirm `config.yaml` points at the right `input_dir`, `output_dir`, and
   `course_preset` for this exam.

## Each grading cycle

1. **Drop the scans in.** Put the scanned exam PDFs (one PDF per student) in the
   `input_dir` from `config.yaml`. Nothing else should be in that folder.

2. **Check the masking config matches this exam template.** Open `config.yaml`
   and confirm `redaction.header_box` / `redaction.regex_patterns` cover where the
   student name and SID appear on *this* exam. If the template changed since last
   time, update them first.

3. **Dry-run to estimate cost and time:**

   ```bash
   uv run ocr-grade dry-run --config config.yaml
   ```

   Read the estimated cost and projected wall time. If they look wrong (e.g. far
   more pages than expected), stop and check `input_dir`.

4. **Run the batch:**

   ```bash
   uv run ocr-grade run --config config.yaml
   ```

   Watch the progress bar and the live running cost. It writes one
   `{course}_{exam}_{student_id}.pdf` per student into `output_dir`, plus
   `run_report.md`.

5. **Read `out/run_report.md`.** Confirm pages processed matches expectations and
   the **Failures** table is empty. If there are failures, each row names the exam
   and reason — fix the cause (see `OPERATIONS.md` → Troubleshoot) and re-run
   (already-done pages are reused from cache, not re-billed).

6. **Spot-check 2–3 output PDFs.** Open them and verify:
   - the student name / SID is **blacked out** on every scan page (privacy), and
   - the transcript text matches the handwriting and the prompt/answer split looks
     right.

   If identity is **not** masked, do not distribute. Fix `redaction.*` in
   `config.yaml`, purge the affected exam (step 8), and re-run.

7. **Upload to Gradescope.** Use the interleaved PDFs from `output_dir`.

8. **Clean up when done.** Once grading is complete and you no longer need the
   scratch (originals, page PNGs, identity sidecars, OCR cache), purge each exam
   by its sha (the subfolder name under `cache_dir`):

   ```bash
   uv run ocr-grade purge --batch <sha> --config config.yaml
   ```

   This removes cached OCR + intermediate artifacts but **keeps** the finished
   output PDFs. See `docs/data-policy.md` for what was stored where.

## Quarterly

- Rotate the Mistral API key (`docs/mistral-setup.md` → Key hygiene).
- Re-confirm Mistral's data/retention settings still match policy
  (`docs/data-policy.md`).
