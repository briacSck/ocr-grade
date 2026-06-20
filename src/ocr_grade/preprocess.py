"""Rasterize PDF pages to images and clean them up.

`rasterize(exam_file, dpi, cache_dir)` renders each page to a PNG via PyMuPDF
(no Poppler/native binary needed), enforces Mistral's 20 MB per-image limit,
and caches the PNGs under ``cache_dir/<exam_sha>/page_<n>.png``. `clean(image,
steps)` applies deskew / denoise / adaptive contrast, each toggleable via
``settings.preprocess_steps``.
"""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import fitz  # PyMuPDF
import numpy as np
from pydantic import BaseModel, ConfigDict

from .config import PreprocessStepsSettings
from .ingestion import MAX_IMAGE_BYTES, ExamFile, IngestionError


class PageImage(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    page_number: int  # 1-indexed
    image: np.ndarray  # BGR
    path: Path | None = None


def rasterize(
    exam_file: ExamFile,
    dpi: int,
    cache_dir: str | Path,
) -> list[PageImage]:
    """Render every page of ``exam_file`` to a cached PNG and return the images."""
    out_dir = Path(cache_dir) / exam_file.sha256
    out_dir.mkdir(parents=True, exist_ok=True)

    pages: list[PageImage] = []
    with fitz.open(exam_file.path) as doc:
        width = len(str(doc.page_count))
        for index, page in enumerate(doc, start=1):
            pix = page.get_pixmap(dpi=dpi)
            png = pix.tobytes("png")
            if len(png) > MAX_IMAGE_BYTES:
                raise IngestionError(
                    f"{exam_file.path.name} page {index} renders to "
                    f"{len(png) / 1024 / 1024:.1f} MB at {dpi} DPI, over Mistral's "
                    f"{MAX_IMAGE_BYTES // 1024 // 1024} MB per-image limit; "
                    "lower `dpi` in the config or split the PDF."
                )
            png_path = out_dir / f"page_{index:0{width}d}.png"
            png_path.write_bytes(png)
            array = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_COLOR)
            pages.append(PageImage(page_number=index, image=array, path=png_path))

    return pages


def _deskew(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=200)
    if lines is None:
        return image

    angles: list[float] = []
    for rho_theta in lines[:, 0]:
        theta = rho_theta[1]
        deg = math.degrees(theta) - 90.0  # 0 for a horizontal line
        if -45.0 < deg < 45.0:
            angles.append(deg)
    if not angles:
        return image

    angle = float(np.median(angles))
    if abs(angle) < 0.1:
        return image

    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(
        image, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )


def _denoise(image: np.ndarray) -> np.ndarray:
    return cv2.fastNlMeansDenoisingColored(image, None, 10, 10, 7, 21)


def _contrast(image: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    luminance, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    luminance = clahe.apply(luminance)
    merged = cv2.merge((luminance, a, b))
    return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)


def clean(image: np.ndarray, steps: PreprocessStepsSettings) -> np.ndarray:
    """Apply the enabled cleanup stages and return a new image (no disk writes)."""
    result = image
    if steps.deskew:
        result = _deskew(result)
    if steps.denoise:
        result = _denoise(result)
    if steps.contrast:
        result = _contrast(result)
    return result


# Map clockwise degrees -> the matching cv2 rotate constant. Clockwise so the
# value lines up 1:1 with a PDF /Rotate increment (see pdf_assembler).
_ROTATE_OPS = {
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


def rotate_image(image: np.ndarray, degrees_cw: int) -> np.ndarray:
    """Rotate ``image`` clockwise by 0/90/180/270 degrees (no-op for 0)."""
    op = _ROTATE_OPS.get(degrees_cw % 360)
    return image if op is None else cv2.rotate(image, op)


def text_is_horizontal(image: np.ndarray) -> bool:
    """True if text lines run horizontally (page is portrait-upright or upside down).

    Scale-free heuristic: lines of text create strong banding along the axis
    perpendicular to the text direction. We compare the coefficient of variation
    of the row-ink profile against the column-ink profile; the stronger banding
    marks the text-line axis. This reliably tells 0/180 from 90/270, but NOT
    which way is up -- that is resolved by the identity OCR in `redaction`.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    rows = binary.sum(axis=1).astype(float)
    cols = binary.sum(axis=0).astype(float)
    row_cv = rows.std() / (rows.mean() + 1e-6)
    col_cv = cols.std() / (cols.mean() + 1e-6)
    return bool(row_cv >= col_cv)
