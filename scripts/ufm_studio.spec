# -*- mode: python ; coding: utf-8 -*-
"""Reproducible native bundle; exclude unrelated ICU DLLs discovered on PATH."""
import os
from pathlib import Path
import subprocess

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

root = Path(SPECPATH).parent
node_dir = root / ".runtime" / "node-v24.22.1-win-x64"
node_exe = node_dir / "node.exe"
node_license = node_dir / "LICENSE"
if not node_exe.is_file() or not node_license.is_file():
    raise RuntimeError("Run scripts/prepare_node_runtime.ps1 before building UFM Studio.")
node_version = subprocess.run(
    [str(node_exe), "--version"], capture_output=True, text=True, timeout=5, check=True
).stdout.strip()
if node_version != "v24.22.1":
    raise RuntimeError(f"Unexpected bundled Node runtime: {node_version}")
version_file = os.environ.get("UFM_VERSION_FILE")
if not version_file or not Path(version_file).is_file():
    raise RuntimeError("Build UFM Studio through scripts/build_studio.ps1 to supply version metadata.")

data = collect_data_files("ufm") + collect_data_files("alembic")
data += copy_metadata("keyring") + copy_metadata("universal-filament-manager")
data += [(str(root / "src/ufm/infrastructure/persistence/migrations"),
          "ufm/infrastructure/persistence/migrations"),
         (str(node_license), "third-party/node")]
a = Analysis(
    [str(root / "scripts/studio_entry.py")], pathex=[str(root / "src")],
    binaries=[(str(node_exe), "runtime")], datas=data,
    hiddenimports=[
        "alembic.ddl.sqlite",
        "keyring.backends.Windows",
        # keyring loads this OS credential provider through a runtime import.
        "win32ctypes.pywin32.pywintypes",
        "win32ctypes.pywin32.win32api",
        "win32ctypes.pywin32.win32cred",
        "win32ctypes.core._winerrors",
        "win32ctypes.core.compat",
        # win32ctypes' MetaPathFinder redirects these virtual modules to its
        # ctypes implementation; PyInstaller cannot infer that redirection.
        "win32ctypes.core.ctypes._authentication",
        "win32ctypes.core.ctypes._common",
        "win32ctypes.core.ctypes._dll",
        "win32ctypes.core.ctypes._nl_support",
        "win32ctypes.core.ctypes._resource",
        "win32ctypes.core.ctypes._system_information",
        "win32ctypes.core.ctypes._time",
        "win32ctypes.core.ctypes._util",
    ],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["mypy", "pytest", "ruff", "tkinter"], noarchive=False,
)
# Qt 6.12 Windows imports the unversioned Windows ICU API. A developer tool's
# icuuc.dll with suffixed ICU 78 symbols can otherwise shadow System32/icuuc.dll
# and produce WinError 127. Windows system DLLs must stay OS-owned.
a.binaries = [entry for entry in a.binaries
              if Path(entry[0]).name.casefold() not in {"icuuc.dll", "icudt78.dll"}]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="UFM Studio", debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    version=version_file,
    disable_windowed_traceback=False, icon=str(root / "src/ufm/ui/assets/ufm.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="UFM Studio")
