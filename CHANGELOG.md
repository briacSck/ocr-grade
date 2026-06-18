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
