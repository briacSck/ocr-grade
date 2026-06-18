from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from ocr_grade.config import load_settings

EXAMPLE_CONFIG = Path("config.example.yaml")


def test_load_example_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key-123")

    settings = load_settings(EXAMPLE_CONFIG)

    assert settings.dpi == 300
    assert settings.course_preset == "PE101"
    assert settings.mistral.model == "mistral-ocr-latest"
    assert settings.preprocess_steps.deskew is True
    assert settings.mistral.api_key.get_secret_value() == "test-key-123"


def test_env_overrides_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key-123")
    monkeypatch.setenv("OCR_GRADE__MISTRAL__MODEL", "mistral-ocr-other")

    settings = load_settings(EXAMPLE_CONFIG)

    assert settings.mistral.model == "mistral-ocr-other"


def test_bad_dpi_raises_validation_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key-123")
    bad_config = yaml.safe_load(EXAMPLE_CONFIG.read_text())
    bad_config["dpi"] = -5
    config_path = tmp_path / "bad_dpi.yaml"
    config_path.write_text(yaml.safe_dump(bad_config))

    with pytest.raises(ValidationError):
        load_settings(config_path)


def test_missing_api_key_raises_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)

    with pytest.raises(ValidationError, match="api_key"):
        load_settings(EXAMPLE_CONFIG)
