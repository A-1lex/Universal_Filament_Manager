"""Explicit composition; importing this module starts no workers or services."""

import logging
from dataclasses import dataclass

from ufm.application.ports.secrets import SecretStore
from ufm.bootstrap.settings import AppSettings
from ufm.infrastructure.logging import configure_logging
from ufm.infrastructure.secrets import OSSecretStore
from ufm.platform.common.paths import AppPaths
from ufm.ui.i18n import Translator, validate_catalogs


@dataclass(frozen=True, slots=True)
class AppContainer:
    settings: AppSettings
    paths: AppPaths
    translator: Translator
    secrets: SecretStore
    logger: logging.Logger

    def close(self) -> None:
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
            handler.close()


def create_container(
    settings: AppSettings, paths: AppPaths, *, check_only: bool = False
) -> AppContainer:
    if check_only:
        validate_catalogs()
    if not check_only:
        paths.create()
    logger = configure_logging(None if check_only else paths.logs, settings.log_level)
    return AppContainer(settings, paths, Translator(settings.locale), OSSecretStore(), logger)
