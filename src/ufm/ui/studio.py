"""Native Studio entry point. Qt is an optional dependency, never a web view."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from ufm.bootstrap.settings import AppSettings, SettingsError, load_settings
from ufm.platform.common.paths import AppPaths


def resolve_settings(
    data_dir: Path | None, locale_override: str | None,
) -> tuple[AppPaths, AppSettings]:
    """Load Studio preferences from its user config; an explicit CLI locale wins."""
    paths = AppPaths.resolve(data_dir)
    settings = load_settings(paths.config / "settings.json")
    if locale_override is not None:
        settings = AppSettings.model_validate({**settings.model_dump(), "locale": locale_override})
    return paths, settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ufm-studio", allow_abbrev=False)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--locale", choices=("uk-UA", "en-US"), default=None)
    parser.add_argument("--capture", type=Path, help="Save an offscreen preview and exit")
    args = parser.parse_args(argv)
    if args.capture is not None and args.data_dir is None:
        parser.error("--capture requires an explicit --data-dir")
    try:
        from ufm.ui.studio_window import run
    except ImportError as error:
        if args.capture is not None:
            args.capture.parent.mkdir(parents=True, exist_ok=True)
            args.capture.with_suffix(".startup.txt").write_text(
                f"{type(error).__name__}: module={error.name}", encoding="utf-8",
            )
        print("Install the desktop extra: pip install -e '.[desktop]'", file=sys.stderr)
        return 1
    try:
        paths, settings = resolve_settings(args.data_dir, args.locale)
    except (SettingsError, ValidationError):
        print("UFM Studio: локальні налаштування пошкоджені або мають невідомі поля.",
              file=sys.stderr)
        return 2
    return run(paths, settings, args.capture)


if __name__ == "__main__":
    raise SystemExit(main())
