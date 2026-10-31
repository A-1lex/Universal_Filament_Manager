"""Application-owned paths, resolved only at explicit startup."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppPaths:
    data: Path
    config: Path
    logs: Path
    cache: Path

    @classmethod
    def resolve(cls, root: Path | None = None) -> "AppPaths":
        if root is not None:
            base = root.expanduser().resolve()
            return cls(base / "data", base / "config", base / "logs", base / "cache")
        from platformdirs import PlatformDirs

        dirs = PlatformDirs("UniversalFilamentManager", appauthor=False)
        return cls(
            dirs.user_data_path,
            dirs.user_config_path,
            dirs.user_log_path,
            dirs.user_cache_path,
        )

    def create(self) -> None:
        for path in (self.data, self.config, self.logs, self.cache):
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
