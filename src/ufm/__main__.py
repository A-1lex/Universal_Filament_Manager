"""Allow ``python -m ufm`` to use the composition-root entry point."""

from ufm.bootstrap.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

