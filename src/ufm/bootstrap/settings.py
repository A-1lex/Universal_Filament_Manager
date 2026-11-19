"""Validated non-secret settings. No implicit environment or file loading."""

import json
import os
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_SETTINGS_BYTES = 64 * 1024
Locale = Literal["uk-UA", "en-US"]
Theme = Literal["light", "dark"]
InventoryColumn = Literal[
    "name", "material", "color", "location", "remaining", "state", "health",
]


class SettingsError(ValueError):
    """A safe, stable error that never echoes invalid configuration content."""

    def __init__(self) -> None:
        super().__init__("settings.invalid")


class AppSettings(BaseModel):
    """Phase 0 has no network listener, updater, or automatic stock deduction."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    locale: Locale = "uk-UA"
    theme: Theme = "light"
    inventory_columns: tuple[InventoryColumn, ...] = (
        "name", "material", "color", "location", "remaining", "state", "health",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    sqlite_busy_timeout_ms: int = Field(default=5000, ge=1, le=60_000)
    local_api_enabled: bool = False
    local_api_port: int = Field(default=7912, ge=1, le=65535)


def load_settings(path: Path | None = None) -> AppSettings:
    """Missing file means defaults; an existing malformed file is never ignored."""
    if path is None:
        return AppSettings()
    try:
        with path.open("rb") as stream:
            content = stream.read(MAX_SETTINGS_BYTES + 1)
    except FileNotFoundError:
        return AppSettings()
    except OSError:
        raise SettingsError() from None
    if len(content) > MAX_SETTINGS_BYTES:
        raise SettingsError()
    try:
        # A JSON object with strict fields; credentials cannot hide in extra keys.
        payload: object = json.loads(content)
        if not isinstance(payload, dict):
            raise SettingsError()
        return AppSettings.model_validate_json(content)
    except ValueError:
        raise SettingsError() from None


def save_settings(settings: AppSettings, path: Path) -> None:
    """Atomically persist validated non-secret preferences in the config folder."""
    if not isinstance(settings, AppSettings):
        raise SettingsError()
    content = (settings.model_dump_json(indent=2) + "\n").encode("utf-8")
    if len(content) > MAX_SETTINGS_BYTES:
        raise SettingsError()
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=".settings-", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != "nt":
            temporary.chmod(0o600)
        os.replace(temporary, path)
    except OSError:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise SettingsError() from None
