"""Загрузка настроек из .env и config.toml."""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


def _flatten_toml(data: dict[str, Any], fields: set[str], prefix: str = "") -> dict[str, Any]:
    """Плоские ключи и вложенные таблицы (`[ollama] base_url` → `ollama_base_url`)."""
    found: dict[str, Any] = {}
    for key, value in data.items():
        lowered = str(key).lower()
        qualified = f"{prefix}_{lowered}" if prefix else lowered
        if isinstance(value, dict):
            found.update(_flatten_toml(value, fields, qualified))
            continue
        if qualified in fields:
            found[qualified] = value
        elif lowered in fields:
            found[lowered] = value
    return found


def _read_config_toml(path: Path, fields: set[str]) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    if not isinstance(raw, dict):
        return {}
    return _flatten_toml(raw, fields)


class _TomlFileSettingsSource(PydanticBaseSettingsSource):
    """config.toml ниже .env и переменных окружения по приоритету."""

    def __init__(self, settings_cls: type[BaseSettings], toml_file: Path) -> None:
        super().__init__(settings_cls)
        self._data = _read_config_toml(toml_file, set(settings_cls.model_fields))

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        if field_name in self._data:
            return self._data[field_name], field_name, False
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        return dict(self._data)


class Settings(BaseSettings):
    """Настройки агента. Окружение и .env перекрывают config.toml."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:14b"
    plans_dir: str = "./plans"
    logs_dir: str = "./logs"
    max_step_retries: int = 3

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            _TomlFileSettingsSource(settings_cls, Path("config.toml")),
            file_secret_settings,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Синглтон настроек."""
    return Settings()
