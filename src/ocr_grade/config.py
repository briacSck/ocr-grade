"""Typed settings loaded from config.yaml + environment variables.

Precedence (highest to lowest): explicit constructor kwargs > environment
variables (OCR_GRADE__<FIELD>__<NESTED_FIELD>, e.g. OCR_GRADE__MISTRAL__MODEL)
> the yaml config file > field defaults. The Mistral API key is the one
exception: it is always read from the plain MISTRAL_API_KEY env var (injected
via a model validator, not the nested-delimiter convention) and never from
the yaml file, so it can never be accidentally committed in config.yaml.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


class RedactionSettings(BaseModel):
    header_box: tuple[int, int, int, int] | None = None
    regex_patterns: list[str] = Field(default_factory=list)
    # Auto-detect each exam's page rotation and normalize it to upright before
    # masking, so identity is found wherever the scanner placed the header.
    # Only used when header_box is null (a fixed box implies a known orientation).
    auto_orient: bool = True


class MistralSettings(BaseModel):
    api_key: SecretStr
    model: str = "mistral-ocr-latest"
    base_url: str | None = None
    timeout_s: int = 60
    include_image_base64: bool = False


class PreprocessStepsSettings(BaseModel):
    deskew: bool = True
    denoise: bool = True
    contrast: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OCR_GRADE__",
        env_nested_delimiter="__",
        yaml_file="config.yaml",
        extra="forbid",
    )

    input_dir: Path
    output_dir: Path
    cache_dir: Path
    dpi: int = Field(default=300, ge=150)
    # Minimum estimated native scan DPI to accept; files below this are flagged
    # in ingestion. Default mirrors ingestion.MIN_NATIVE_DPI; lower it (e.g. 140)
    # for scanners that export just under the usual 150.
    min_native_dpi: int = Field(default=150, ge=72)
    course_preset: str
    redaction: RedactionSettings = Field(default_factory=RedactionSettings)
    mistral: MistralSettings
    mistral_price_per_page: float = Field(default=0.001, ge=0)
    preprocess_steps: PreprocessStepsSettings = Field(default_factory=PreprocessStepsSettings)

    @model_validator(mode="before")
    @classmethod
    def _inject_mistral_api_key(cls, data: Any) -> Any:
        # pydantic-settings' nested-delimiter env convention would otherwise
        # require OCR_GRADE__MISTRAL__API_KEY; we deliberately keep the
        # single plain MISTRAL_API_KEY env var (matching the PRD and the
        # Phase 0 script) so the real secret never has to live in yaml.
        if isinstance(data, dict):
            api_key = os.environ.get("MISTRAL_API_KEY")
            if api_key is not None:
                mistral = dict(data.get("mistral") or {})
                mistral["api_key"] = api_key
                data["mistral"] = mistral
        return data

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        yaml_settings = YamlConfigSettingsSource(
            settings_cls, yaml_file=settings_cls.model_config.get("yaml_file")
        )
        return (init_settings, env_settings, yaml_settings, file_secret_settings)


def load_settings(path: str | Path) -> Settings:
    """Load Settings from the yaml file at `path`, with env var overrides applied."""

    config: Any = {**Settings.model_config, "yaml_file": Path(path)}

    class _Settings(Settings):
        model_config = SettingsConfigDict(**config)

    return _Settings()
