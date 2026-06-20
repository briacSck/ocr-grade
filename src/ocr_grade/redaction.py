"""Local identity masking before any full page is sent to Mistral.

`mask(page_image, settings)` blacks out a configured header bounding box, runs a
cheap header-only OCR pass (behind the `HeaderOCR` seam, stubbable in tests) to
catch identity text that leaks outside that box, masks the header band when a
configured regex matches, and writes a LOCAL-ONLY sidecar recording the masked
regions and the extracted identity strings.

Privacy contract: only the cropped header region is ever sent to Mistral (once,
for the header read). The masked full page that later goes to the main OCR pass
has identity blacked out, and the extracted identity strings are written only to
the local sidecar under the (gitignored) cache dir -- never re-sent.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict

from .config import MistralSettings, Settings
from .preprocess import PageImage, rotate_image, text_is_horizontal

# Default header band (top fraction of the page) used for the OCR crop / mask
# when no explicit header_box is configured.
HEADER_BAND_FRACTION = 0.18


class HeaderOCR(Protocol):
    """Reads text from a cropped header image. Stubbable in tests."""

    def read_header(self, header_png: bytes) -> str: ...


class MistralHeaderOCR:
    """Concrete `HeaderOCR` backed by the Mistral OCR API.

    SDK and TLS setup are imported lazily so merely importing this module never
    requires network/credentials, and tests (which stub `HeaderOCR`) never touch
    it. Prompt 6's full Mistral backend may later replace this with a shared
    client.
    """

    def __init__(self, settings: MistralSettings) -> None:
        self._settings = settings

    def read_header(self, header_png: bytes) -> str:
        import base64

        import truststore
        from mistralai.client import Mistral

        truststore.inject_into_ssl()
        client = Mistral(
            api_key=self._settings.api_key.get_secret_value(),
            server_url=self._settings.base_url,
        )
        encoded = base64.b64encode(header_png).decode("ascii")
        response = client.ocr.process(
            model=self._settings.model,
            document={
                "type": "image_url",
                "image_url": f"data:image/png;base64,{encoded}",
            },
        )
        return response.pages[0].markdown if response.pages else ""


class MaskedRegion(BaseModel):
    x: int
    y: int
    w: int
    h: int
    reason: str  # "header_box" | "regex"


class MaskedPage(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    page_number: int
    image: np.ndarray  # masked BGR copy
    regions: list[MaskedRegion]
    identity_strings: list[str]  # LOCAL ONLY -- never re-sent to Mistral
    sidecar_path: Path | None = None


def _fill_black(image: np.ndarray, region: tuple[int, int, int, int]) -> None:
    x, y, w, h = region
    cv2.rectangle(image, (x, y), (x + w, y + h), (0, 0, 0), thickness=-1)


def detect_orientation(
    page_image: PageImage,
    settings: Settings,
    header_ocr: HeaderOCR | None = None,
) -> int:
    """Return the clockwise rotation (0/90/180/270) that makes the page upright.

    The text-line axis is resolved geometrically (`text_is_horizontal`), leaving
    two candidates; we then OCR each candidate's top header band and keep the
    orientation whose band matches the configured identity regexes -- i.e. the
    end where the student header physically is. Falls back to 0 when auto-orient
    is off, a fixed `header_box` is configured, there are no regex patterns, or
    no candidate yields an identity match.
    """
    if not settings.redaction.auto_orient or settings.redaction.header_box is not None:
        return 0
    if not settings.redaction.regex_patterns:
        return 0

    img = page_image.image
    candidates = (0, 180) if text_is_horizontal(img) else (90, 270)
    if header_ocr is None:
        header_ocr = MistralHeaderOCR(settings.mistral)

    hits_by_rotation: dict[int, int] = {}
    for rotation in candidates:
        rotated = rotate_image(img, rotation)
        height, width = rotated.shape[:2]
        crop = rotated[0 : int(height * HEADER_BAND_FRACTION), 0:width]
        ok, buf = cv2.imencode(".png", crop)
        if not ok:
            continue
        text = header_ocr.read_header(buf.tobytes())
        hits_by_rotation[rotation] = sum(
            len(re.findall(pattern, text)) for pattern in settings.redaction.regex_patterns
        )

    if not hits_by_rotation:
        return 0
    best = max(hits_by_rotation.values())
    winners = [rotation for rotation, hits in hits_by_rotation.items() if hits == best]
    # Only rotate on an unambiguous single winner; a tie (identity matched in
    # both candidate bands, or none at all) means we cannot tell -- leave as-is.
    if best == 0 or len(winners) != 1:
        return 0
    return winners[0]


def mask(
    page_image: PageImage,
    settings: Settings,
    header_ocr: HeaderOCR | None = None,
) -> MaskedPage:
    """Mask student identity from a page and return the masked image + sidecar."""
    img = page_image.image.copy()
    height, width = img.shape[:2]
    regions: list[MaskedRegion] = []
    identity_strings: list[str] = []

    header_box = settings.redaction.header_box
    if header_box is not None:
        region = (int(header_box[0]), int(header_box[1]), int(header_box[2]), int(header_box[3]))
    else:
        region = (0, 0, width, int(height * HEADER_BAND_FRACTION))

    # Step 1 -- always mask the explicitly configured header box.
    if header_box is not None:
        _fill_black(img, region)
        regions.append(
            MaskedRegion(x=region[0], y=region[1], w=region[2], h=region[3], reason="header_box")
        )

    # Step 2 -- header-only OCR pass on the ORIGINAL crop, then regex.
    x, y, w, h = region
    crop = page_image.image[y : y + h, x : x + w]
    ok, buf = cv2.imencode(".png", crop)
    if ok:
        if header_ocr is None:
            header_ocr = MistralHeaderOCR(settings.mistral)
        text = header_ocr.read_header(buf.tobytes())
        for pattern in settings.redaction.regex_patterns:
            identity_strings.extend(m.group(0) for m in re.finditer(pattern, text))

    if identity_strings and header_box is None:
        # No fixed box covered it; mask the whole OCR'd header band now.
        _fill_black(img, region)
        regions.append(MaskedRegion(x=x, y=y, w=w, h=h, reason="regex"))
    elif identity_strings:
        regions.append(MaskedRegion(x=x, y=y, w=w, h=h, reason="regex"))

    sidecar_path: Path | None = None
    if page_image.path is not None:
        sidecar_path = page_image.path.with_suffix(".identity.json")
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        sidecar_path.write_text(
            json.dumps(
                {
                    "page_number": page_image.page_number,
                    "regions": [r.model_dump() for r in regions],
                    "identity_strings": identity_strings,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    return MaskedPage(
        page_number=page_image.page_number,
        image=img,
        regions=regions,
        identity_strings=identity_strings,
        sidecar_path=sidecar_path,
    )
