# Deploying the web UI

The web UI (`ocr_grade.web.app:app`) is a small **single-user** FastAPI server:
upload a zip of scanned exam PDFs, it runs the same pipeline as the CLI in a
background task, then offers the interleaved PDFs for download. State lives in
memory + a working directory; there is no database.

## Why a persistent server (not Vercel / serverless)

This app is **stateful and long-running**, so serverless platforms (Vercel,
plain Lambda, etc.) are the wrong fit:

- An OCR batch runs for **minutes** — past serverless function time limits.
- Batch status is held **in one long-lived process**; serverless instances are
  cold/ephemeral and don't share that state across requests.
- It writes scans + output PDFs to a **working directory**; serverless gives only
  an ephemeral `/tmp` that's wiped between invocations (download links would 404).
- PyMuPDF + OpenCV are heavy native deps that strain serverless bundle limits.

Deploy it as an always-on container instead. The `Dockerfile` at the repo root is
the package format Render and Fly build for you — **you don't run Docker
yourself**.

## Prerequisites (all targets)

1. **A real `config.yaml`** — course preset, redaction/masking config, and
   `mistral.model`. Masking is read from this file and is never guessed, so get it
   right for your exam template before going live. Either commit a `config.yaml`
   or mount one at deploy time.
2. **Secrets / env vars:**
   - `MISTRAL_API_KEY` — same key the CLI uses.
   - `OCR_GRADE_WEB_USER`, `OCR_GRADE_WEB_PASSWORD` — the login.
   - Optional: `OCR_GRADE_WEB_WORKDIR` (default `web-work`),
     `OCR_GRADE_WEB_BASE_CONFIG` (default `config.yaml`),
     `OCR_GRADE_WEB_MAX_UPLOAD_MB` (default `200`).

> **Single user.** This is intentionally one login (Prof. Chang) — no TA or
> multi-user accounts. Keep the `OCR_GRADE_WEB_USER` / `OCR_GRADE_WEB_PASSWORD`
> private; treat the password like the API key.

> **Always serve over HTTPS.** HTTP Basic credentials are sent on every request.
> Render and Fly terminate TLS for you; on a VPS put Caddy or nginx in front.

## Render (recommended)

Easiest path for a non-DevOps owner; gives an HTTPS URL and a secrets UI.

1. Push this repo to GitHub.
2. Render → **New → Web Service** → connect the repo.
3. **Runtime: Docker** (Render auto-detects the `Dockerfile`).
4. **Environment** → add `MISTRAL_API_KEY`, `OCR_GRADE_WEB_USER`,
   `OCR_GRADE_WEB_PASSWORD` (and provide a `config.yaml` — commit one, or add it as
   a Render Secret File mounted at `/app/config.yaml`).
5. **Health check path:** `/healthz`.
6. Deploy. Render builds the image and serves it at an `https://…onrender.com`
   URL. That URL + the single login is all Prof. Chang needs.

Note: Render's filesystem is ephemeral — finished batches don't survive a
restart/redeploy. That matches the "no persistence" design; just re-download
before a redeploy. Add a Render Disk if you want batches to persist.

## Fly.io

1. `fly launch` in the repo (it detects the `Dockerfile`; decline to deploy yet).
2. Set secrets:
   ```bash
   fly secrets set MISTRAL_API_KEY=… OCR_GRADE_WEB_USER=… OCR_GRADE_WEB_PASSWORD=…
   ```
3. Provide `config.yaml` (commit it, or mount via a Fly volume).
4. Set the health check to `GET /healthz` in `fly.toml`, then `fly deploy`.

Fly's machine filesystem is ephemeral too; attach a volume mounted at the
`OCR_GRADE_WEB_WORKDIR` path only if you want batches to outlive a restart.

## Small VPS

```bash
docker build -t ocr-grade-web .
docker run -d --restart unless-stopped -p 8000:8000 \
  -e MISTRAL_API_KEY=… \
  -e OCR_GRADE_WEB_USER=… \
  -e OCR_GRADE_WEB_PASSWORD=… \
  -v "$PWD/config.yaml:/app/config.yaml:ro" \
  ocr-grade-web
```

Put **Caddy or nginx** in front for TLS (a `caddy reverse-proxy --to :8000` with a
real domain is enough). Without HTTPS the Basic-auth login is exposed in transit.

## Local smoke test

```bash
OCR_GRADE_WEB_USER=me OCR_GRADE_WEB_PASSWORD=secret \
  uv run uvicorn ocr_grade.web.app:app --port 8000
# GET /healthz -> 200; open http://localhost:8000/ and sign in.
```
