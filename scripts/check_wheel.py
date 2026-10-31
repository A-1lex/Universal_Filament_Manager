"""CI: install the built wheel into an isolated environment and run outside src."""

import os
import subprocess
import tempfile
import venv
from pathlib import Path


def main() -> None:
    wheels = list(Path("dist").glob("universal_filament_manager-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError("Expected exactly one built UFM wheel")
    wheel = wheels[0].resolve()
    with tempfile.TemporaryDirectory(prefix="ufm-wheel-") as directory:
        root = Path(directory)
        # Install the wheel as a user would, including its declared runtime dependencies.
        venv.EnvBuilder(with_pip=True).create(root / "env")
        python = root / "env" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env["PYTHONUTF8"] = "1"
        subprocess.run(
            [str(python), "-m", "pip", "install", "--force-reinstall", str(wheel)],
            cwd=root,
            env=env,
            check=True,
        )
        # A shared editable checkout must not mask an empty/broken wheel.
        origin_check = (
            "import pathlib, sys, ufm, ufm.ui.i18n; "
            "root = pathlib.Path(sys.prefix).resolve(); "
            "assert all(root in pathlib.Path(module.__file__).resolve().parents "
            "for module in (ufm, ufm.ui.i18n)), 'Imported UFM outside wheel environment'"
        )
        subprocess.run(
            [str(python), "-X", "utf8", "-I", "-c", origin_check],
            cwd=root, env=env, check=True,
        )
        migration_check = (
            "from pathlib import Path; "
            "from ufm.infrastructure.persistence.sqlite import create_sqlite_engine; "
            "from ufm.infrastructure.persistence.sqlite.migrate import LATEST_REVISION, migrate_database; "
            "engine=create_sqlite_engine(Path('wheel.sqlite3')); "
            "assert migrate_database(engine) == LATEST_REVISION; "
            "assert migrate_database(engine) == LATEST_REVISION; engine.dispose()"
        )
        subprocess.run(
            [str(python), "-X", "utf8", "-I", "-c", migration_check],
            cwd=root, env=env, check=True,
        )
        component_check = (
            "from importlib.resources import files; "
            "from ufm.integrations.catalog import load_material_catalog; "
            "from ufm.integrations.qr import spool_label_svg, spool_label_text, parse_spool_label; "
            "from ufm.domain.value_objects import EntityId; "
            "assert len(load_material_catalog()) == 34; "
            "assert 'MIT License' in files('ufm.integrations.catalog').joinpath('LICENSE.spoolmandb.txt').read_text(); "
            "assert 'Lars Heuer' in files('ufm.integrations.qr').joinpath('LICENSE.segno.txt').read_text(); "
            "identity=EntityId.parse('01234567-89ab-4cde-8123-0123456789ab'); "
            "assert parse_spool_label(spool_label_text(identity)) == identity; "
            "assert b'<svg' in spool_label_svg(identity)"
        )
        subprocess.run(
            [str(python), "-X", "utf8", "-I", "-c", component_check],
            cwd=root, env=env, check=True,
        )
        for locale in ("uk-UA", "en-US"):
            subprocess.run(
                [str(python), "-X", "utf8", "-I", "-m", "ufm", "--check", "--locale", locale,
                 "--data-dir", str(root / "app")],
                cwd=root,
                env=env,
                check=True,
            )
        if (root / "app").exists():
            raise RuntimeError("Check-only startup unexpectedly wrote application directories")


if __name__ == "__main__":
    main()
