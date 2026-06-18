# Container image for the single-user web UI (ocr_grade.web.app:app).
# Render and Fly.io build this for you — see docs/deploy.md. You do not need to
# run Docker locally to deploy.
FROM python:3.11-slim

# OpenCV (opencv-python) needs these system libraries at runtime; PyMuPDF does
# not need anything extra (it bundles its own renderer — no Poppler/GTK).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# uv for fast, locked installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies from the lockfile first (better layer caching).
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# config.yaml is NOT baked in — provide it at deploy time (mount or commit your
# own), along with MISTRAL_API_KEY / OCR_GRADE_WEB_USER / OCR_GRADE_WEB_PASSWORD.
EXPOSE 8000
CMD ["uvicorn", "ocr_grade.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
