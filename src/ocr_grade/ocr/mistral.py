"""Mistral OCR backend (sole concrete `OCRBackend`).

Sends a single masked page inline as a base64 `image_url` data URI to Mistral's
`/v1/ocr` endpoint (no `/files` upload, no public hosting), parses the returned
markdown into structured `OCRResult` blocks, and retries transient failures with
tenacity. Credentials/model/base_url/timeout all come from settings — nothing is
hardcoded except the documented default model alias in config.
"""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Callable
from pathlib import Path

import truststore
from markdown_it import MarkdownIt
from mistralai.client import Mistral
from mistralai.client.errors.sdkerror import SDKError
from mistralai.client.models.ocrresponse import OCRResponse
from tenacity import Retrying, retry_if_exception, stop_after_attempt

from ..config import Settings
from .base import OCRBlock, OCRResult, PageMeta

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _status_of(exc: BaseException) -> int | None:
    if isinstance(exc, SDKError):
        return exc.raw_response.status_code
    return None


def _is_retryable(exc: BaseException) -> bool:
    status = _status_of(exc)
    return status is not None and (status == 429 or 500 <= status < 600)


def _wait_retry_after(retry_state: object) -> float:
    """Honor a numeric `Retry-After` header, else exponential backoff (cap 30s)."""
    outcome = getattr(retry_state, "outcome", None)
    exc = outcome.exception() if outcome is not None else None
    if isinstance(exc, SDKError):
        retry_after = exc.raw_response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
    attempt = getattr(retry_state, "attempt_number", 1)
    return float(min(2 ** (attempt - 1), 30))


def _parse_blocks(markdown: str) -> list[OCRBlock]:
    """Tag each top-level markdown block as heading / paragraph / list."""
    tokens = MarkdownIt().parse(markdown)
    blocks: list[OCRBlock] = []
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok.level != 0 or not tok.type.endswith("_open"):
            i += 1
            continue

        if tok.type == "heading_open":
            text = tokens[i + 1].content if i + 1 < n else ""
            blocks.append(OCRBlock(type="heading", text=text))
            i += 3  # heading_open, inline, heading_close
            continue

        if tok.type == "paragraph_open":
            text = tokens[i + 1].content if i + 1 < n else ""
            blocks.append(OCRBlock(type="paragraph", text=text))
            i += 3
            continue

        if tok.type in ("bullet_list_open", "ordered_list_open"):
            close = "bullet_list_close" if tok.type == "bullet_list_open" else "ordered_list_close"
            items: list[str] = []
            j = i + 1
            while j < n and not (tokens[j].type == close and tokens[j].level == tok.level):
                if tokens[j].type == "inline":
                    items.append(tokens[j].content)
                j += 1
            blocks.append(OCRBlock(type="list", text="\n".join(items)))
            i = j + 1
            continue

        i += 1

    return blocks


class MistralOCRBackend:
    """Transcribes a masked page image via the Mistral OCR API."""

    name = "mistral"

    def __init__(
        self,
        settings: Settings,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._mistral = settings.mistral
        self._price_per_page = settings.mistral_price_per_page
        truststore.inject_into_ssl()
        self._client = Mistral(
            api_key=self._mistral.api_key.get_secret_value(),
            server_url=self._mistral.base_url,
        )
        self._retrying = Retrying(
            stop=stop_after_attempt(5),
            retry=retry_if_exception(_is_retryable),
            wait=_wait_retry_after,
            sleep=sleep,
            reraise=True,
        )

    @property
    def cache_fingerprint(self) -> str:
        params = json.dumps(
            {"include_image_base64": self._mistral.include_image_base64},
            sort_keys=True,
        )
        return f"{self._mistral.model}|{params}"

    def _process(self, data_uri: str) -> OCRResponse:
        return self._client.ocr.process(
            model=self._mistral.model,
            document={"type": "image_url", "image_url": data_uri},
            include_image_base64=self._mistral.include_image_base64,
            retries=None,  # tenacity owns retrying
            timeout_ms=self._mistral.timeout_s * 1000,
        )

    def transcribe(self, image_path: Path, page_meta: PageMeta) -> OCRResult:
        encoded = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
        data_uri = f"data:image/png;base64,{encoded}"

        start = time.perf_counter()
        response = self._retrying(self._process, data_uri)
        latency_ms = (time.perf_counter() - start) * 1000

        pages = getattr(response, "pages", None) or []
        markdown = pages[0].markdown if pages else ""
        return OCRResult(
            markdown_text=markdown,
            blocks=_parse_blocks(markdown),
            raw_response=response.model_dump(mode="json"),
            cost_usd=self._price_per_page,
            latency_ms=latency_ms,
        )
