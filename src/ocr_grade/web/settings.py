"""Settings for the single-user web UI.

Read only from the environment (prefix ``OCR_GRADE_WEB_``), kept separate from
the pipeline `ocr_grade.config.Settings` (prefix ``OCR_GRADE__``) so the two
never collide. The Mistral key still comes from the plain ``MISTRAL_API_KEY``
env var via the pipeline config — it is not duplicated here.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class WebSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OCR_GRADE_WEB_", extra="ignore")

    # HTTP Basic credentials. If either is unset the app refuses all requests
    # (fail closed) rather than serving an unauthenticated instance.
    user: str | None = None
    password: SecretStr | None = None

    # Pipeline config to load per batch (course preset, redaction/masking, model).
    base_config: Path = Path("config.yaml")

    # Root for per-batch working directories (input/out/cache). No state lives
    # outside this tree — there is no database.
    workdir: Path = Path("web-work")

    # Reject uploads whose zip or uncompressed contents exceed this size.
    max_upload_mb: int = 200

    # Optional default course override applied to every batch.
    course: str | None = None

    @property
    def auth_configured(self) -> bool:
        return bool(self.user) and self.password is not None


@lru_cache
def get_web_settings() -> WebSettings:
    """Cached accessor used as a FastAPI dependency (clear in tests via cache_clear)."""
    return WebSettings()
