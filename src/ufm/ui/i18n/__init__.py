"""Resource-based Ukrainian/English translations with deterministic fallback."""

import json
from importlib.resources import files
from string import Formatter

SUPPORTED_LOCALES = ("uk-UA", "en-US")
FALLBACK_LOCALE = "en-US"
_REQUIRED_KEYS = frozenset({
    "app.title", "app.check_ok", "app.foundation_ready", "cli.help",
    "error.arguments", "error.settings", "error.startup", "error.localization",
})


class TranslationError(ValueError):
    pass


def load_catalog(locale: str) -> dict[str, str]:
    selected = locale if locale in SUPPORTED_LOCALES else FALLBACK_LOCALE
    try:
        resource = files(__package__).joinpath(f"{selected}.json")
        payload: object = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise TranslationError("i18n.invalid_catalog") from None
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in payload.items()
    ):
        raise TranslationError("i18n.invalid_catalog")
    return {str(key): str(value) for key, value in payload.items()}


def placeholders(template: str) -> frozenset[str]:
    """Only plain named fields are allowed: no attribute/index traversal."""
    result: set[str] = set()
    try:
        for _, name, format_spec, conversion in Formatter().parse(template):
            if name is None:
                continue
            if not name.isidentifier() or format_spec or conversion:
                raise TranslationError("i18n.invalid_placeholder")
            result.add(name)
    except ValueError:
        raise TranslationError("i18n.invalid_placeholder") from None
    return frozenset(result)


def validate_catalogs() -> None:
    english = load_catalog(FALLBACK_LOCALE)
    for locale in SUPPORTED_LOCALES:
        catalog = load_catalog(locale)
        if catalog.keys() != english.keys():
            raise TranslationError("i18n.key_mismatch")
        for key, template in catalog.items():
            if not template.strip() or placeholders(template) != placeholders(english[key]):
                raise TranslationError("i18n.placeholder_mismatch")


class Translator:
    def __init__(self, locale: str) -> None:
        self._english = load_catalog(FALLBACK_LOCALE)
        self._catalog = load_catalog(locale)
        if not _REQUIRED_KEYS <= self._english.keys():
            raise TranslationError("i18n.missing_required_key")
        for key, template in self._english.items():
            fields = placeholders(template)
            if key in self._catalog and fields != placeholders(self._catalog[key]):
                raise TranslationError("i18n.placeholder_mismatch")

    def template(self, key: str) -> str:
        """Return the raw catalog template for callers that format it later."""
        template = self._catalog.get(key, self._english.get(key))
        if template is None:
            raise TranslationError("i18n.unknown_key")
        return template

    def text(self, key: str, **params: str | int) -> str:
        template = self._catalog.get(key, self._english.get(key))
        if template is None:
            raise TranslationError("i18n.unknown_key")
        if placeholders(template) != params.keys():
            raise TranslationError("i18n.invalid_parameters")
        return template.format_map(params)
