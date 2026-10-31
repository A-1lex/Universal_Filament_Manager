"""Run finalization acceptance from an extracted wheel outside the checkout.

Uses existing development dependencies without downloading anything; the regular
check_wheel.py remains the dependency-installation acceptance check.
"""

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    wheels = list((project / "dist").glob("universal_filament_manager-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError("Expected one UFM wheel")
    tests = project / "tests/integration/test_print_finalization.py"
    with tempfile.TemporaryDirectory(prefix="ufm-finalization-wheel-") as directory:
        root = Path(directory)
        with zipfile.ZipFile(wheels[0]) as wheel:
            for member in wheel.infolist():
                target = (root / member.filename).resolve()
                if not target.is_relative_to(root):
                    raise RuntimeError("Unsafe wheel entry")
            wheel.extractall(root)
        script = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import ufm
import ufm.application.finalization as finalization
root = Path(sys.argv[1]).resolve()
assert Path(ufm.__file__).resolve().is_relative_to(root)
assert Path(finalization.__file__).resolve().is_relative_to(root)
import pytest
raise SystemExit(pytest.main([sys.argv[2], '-q', '--tb=short']))
"""
        subprocess.run(
            [sys.executable, "-I", "-c", script, str(root), str(tests)],
            cwd=root, check=True,
        )


if __name__ == "__main__":
    main()
