"""Frozen executable entry point, kept separate from the importable module."""

from ufm.ui.studio import main

if __name__ == "__main__":
    raise SystemExit(main())
