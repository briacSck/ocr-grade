# Mistral setup

`ocr-grade` transcribes pages through Mistral's OCR API. You need a Mistral
account and an API key.

## 1. Create an account and API key

1. Sign up at <https://console.mistral.ai/>.
2. Open **API Keys** in the console and generate a new key.
3. Copy it once — Mistral only shows the secret at creation time.

## 2. Provide the key via `MISTRAL_API_KEY` (never commit it)

The key is read **only** from the `MISTRAL_API_KEY` environment variable — never
from `config.yaml`, and never hardcoded. Export it from your shell profile:

```bash
# ~/.bashrc / ~/.zshrc
export MISTRAL_API_KEY="…"
```

```powershell
# PowerShell profile ($PROFILE)
$env:MISTRAL_API_KEY = "…"
```

For local development you may instead place it in a **gitignored** `.env` file at
the repo root (`.env` is already in `.gitignore`). Never paste the key into
tracked files, commit messages, or `config.yaml` — the pre-commit secret guard
will block obvious leaks, but treat the key as you would a password.

## 3. Pin the model in `config.yaml`

```yaml
mistral:
  model: mistral-ocr-latest   # alias -> mistral-ocr-2512
```

`mistral-ocr-latest` is an alias that currently resolves to the dated revision
`mistral-ocr-2512`. The alias can shift under you when Mistral ships a new
revision. For reproducible grading runs, pin the **dated** model id and bump it
deliberately after you re-validate OCR quality on a sample:

```yaml
mistral:
  model: mistral-ocr-2512
```

You can also override per run without editing the file:
`OCR_GRADE__MISTRAL__MODEL=mistral-ocr-2512`.

## 4. Key hygiene

- **Rotate** the key on a quarterly schedule.
- **Revoke immediately** in the console if a key is ever leaked or committed, and
  issue a replacement.
- Use a dedicated key for this tool so it can be revoked without disrupting other
  integrations.

See also `docs/data-policy.md` for what leaves your machine and our masking
guarantee.
