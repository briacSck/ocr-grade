"""FastAPI app: a single-user, password-protected exam upload UI.

Thin wrapper over the pipeline — `POST /batches` accepts a zip of scanned exam
PDFs, runs `pipeline.run_batch` in a background task, and exposes a status page
plus download links for the interleaved PDFs. One user (HTTP Basic auth), no
multi-tenant features, no persistence beyond the working directory.
"""

from __future__ import annotations

import io
import secrets
import uuid
import zipfile
from html import escape
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, Form, HTTPException, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from . import batches
from .batches import Batch, UploadError
from .settings import WebSettings, get_web_settings

# Load the API key + login from a local .env file (next to the project) so the
# operator never has to export env vars by hand. Real env vars win (override=False).
load_dotenv()

app = FastAPI(title="ocr-grade")
security = HTTPBasic(auto_error=False)

WebSettingsDep = Annotated[WebSettings, Depends(get_web_settings)]


def require_auth(
    web: WebSettingsDep,
    credentials: Annotated[HTTPBasicCredentials | None, Depends(security)] = None,
) -> str:
    """Validate HTTP Basic credentials against `WebSettings` (constant-time)."""
    if not web.auth_configured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Web auth is not configured (set OCR_GRADE_WEB_USER / _PASSWORD).",
        )
    assert web.user is not None and web.password is not None
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Basic"},
    )
    if credentials is None:
        raise unauthorized
    user_ok = secrets.compare_digest(credentials.username, web.user)
    pw_ok = secrets.compare_digest(credentials.password, web.password.get_secret_value())
    if not (user_ok and pw_ok):
        raise unauthorized
    return credentials.username


AuthDep = Annotated[str, Depends(require_auth)]


def _page(title: str, body: str) -> HTMLResponse:
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{escape(title)}</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:46rem;margin:3rem auto;"
        "padding:0 1rem;line-height:1.5}code{background:#f3f3f3;padding:.1rem .3rem}"
        "a{color:#0b5}</style></head><body>" + body + "</body></html>"
    )
    return HTMLResponse(html)


@app.get("/healthz")
def healthz() -> JSONResponse:
    """Unauthenticated health check for platform probes."""
    return JSONResponse({"ok": True})


@app.get("/", response_class=HTMLResponse)
def index(_user: AuthDep) -> HTMLResponse:
    body = (
        "<h1>ocr-grade</h1>"
        "<p>Upload a <strong>.zip of scanned exam PDFs</strong> (one PDF per student). "
        "Identity is masked locally before any page is sent to Mistral.</p>"
        "<form action='/batches' method='post' enctype='multipart/form-data'>"
        "<p><input type='file' name='archive' accept='.zip' required></p>"
        "<p>Course override (optional): <input type='text' name='course' placeholder='PE101'></p>"
        "<p><button type='submit'>Start batch</button></p>"
        "</form>"
    )
    return _page("ocr-grade — upload", body)


@app.post("/batches")
async def create_batch(
    _user: AuthDep,
    web: WebSettingsDep,
    background_tasks: BackgroundTasks,
    archive: UploadFile,
    course: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    """Accept a folder zip, kick off the pipeline in the background, redirect to status."""
    batch_id = uuid.uuid4().hex
    root = web.workdir / batch_id
    input_dir = root / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    zip_path = root / "upload.zip"
    zip_path.write_bytes(await archive.read())
    try:
        extract_course = course.strip() if course and course.strip() else web.course
        batches.extract_zip(zip_path, input_dir, web.max_upload_mb * 1024 * 1024)
    except UploadError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        zip_path.unlink(missing_ok=True)

    batch = Batch(id=batch_id, root=root, course=extract_course)
    batches.register(batch)
    background_tasks.add_task(batches.run_job, batch_id, web)
    return RedirectResponse(f"/batches/{batch_id}", status_code=status.HTTP_303_SEE_OTHER)


def _status_body(batch: Batch) -> str:
    rows = [
        f"<li>Status: <strong>{escape(batch.status)}</strong></li>",
        f"<li>Pages processed: {batch.pages_done}</li>",
        f"<li>Cost so far: ${batch.cost_usd:.4f}</li>",
    ]
    if batch.model:
        rows.append(f"<li>Model: {escape(batch.model)}</li>")
    body = f"<h1>Batch {escape(batch.id)}</h1><ul>{''.join(rows)}</ul>"

    if batch.status == "done":
        if batch.outputs:
            links = "".join(
                f"<li><a href='/batches/{batch.id}/files/{escape(name)}'>{escape(name)}</a></li>"
                for name in batch.outputs
            )
            body += (
                f"<h2>Transcripts</h2><ul>{links}</ul>"
                f"<p><a href='/batches/{batch.id}/archive'>Download all (.zip)</a></p>"
            )
        else:
            body += "<p>No transcripts were produced.</p>"
    elif batch.status == "failed":
        body += f"<p style='color:#b00'>Failed: {escape(batch.error or 'unknown error')}</p>"

    if batch.failures:
        items = "".join(f"<li>{escape(f)}</li>" for f in batch.failures)
        body += f"<h2>Failures</h2><ul>{items}</ul>"

    body += "<p><a href='/'>&larr; New batch</a></p>"
    return body


@app.get("/batches/{batch_id}", response_class=HTMLResponse)
def batch_status(_user: AuthDep, batch_id: str) -> HTMLResponse:
    batch = batches.get(batch_id)
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown batch.")
    body = _status_body(batch)
    # Auto-refresh while the job is still running.
    if batch.status in ("queued", "running"):
        body = "<meta http-equiv='refresh' content='3'>" + body
    return _page(f"Batch {batch_id}", body)


def _resolve_output(batch: Batch, name: str) -> Path:
    # Whitelist against produced outputs: traversal names are never in the list.
    if name not in batch.outputs:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown file.")
    path = batch.out_dir / name
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="File no longer available.")
    return path


@app.get("/batches/{batch_id}/files/{name}")
def download_file(_user: AuthDep, batch_id: str, name: str) -> Response:
    batch = batches.get(batch_id)
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown batch.")
    path = _resolve_output(batch, name)
    return Response(
        content=path.read_bytes(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@app.get("/batches/{batch_id}/archive")
def download_archive(_user: AuthDep, batch_id: str) -> Response:
    batch = batches.get(batch_id)
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown batch.")
    if not batch.outputs:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No outputs to download.")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in batch.outputs:
            zf.write(_resolve_output(batch, name), arcname=name)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{batch_id}.zip"'},
    )
