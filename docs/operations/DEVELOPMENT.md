# Local development and phase gates

Requires Python 3.12+. Phase 0 introduces Pydantic settings, platformdirs path
selection and an explicitly selected native keyring adapter. Database/GUI packages
are added only in their implementation phases. No printer/API/stock operation
is started by importing the package or running the current foundation CLI.

## Install in a project-owned environment

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m ufm --check --locale uk-UA
```

Linux/macOS:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m ufm --check --locale en-US
```

An already installed newer compatible interpreter may replace 3.12. Installation
downloads packages; this is an explicit setup step, not an action performed by
the app. No developer's absolute interpreter path is stored in project code.
Dependency ranges are declared in pyproject; a tested lock will be generated once
full dependency resolution can actually run. No fabricated lockfile is committed.

## Run and configure

```sh
python -m ufm --help
python -m ufm --version
python -m ufm --check --data-dir .runtime/smoke --locale uk-UA
python -m ufm --data-dir .runtime/local
```

`--check` validates settings/resources and starts/stops the logging composition
without creating application directories, contacting printers or opening an OS
secret backend. Regular startup creates data/config/log/cache directories, writes
a sanitized startup event and reports that only the foundation is available.
There is no GUI or background service yet.

An explicit root stores configuration in `ROOT/config/settings.json`; otherwise
platformdirs resolves the native user config directory. Copy
[example settings](../../examples/settings.json) there if needed. Missing config
uses safe defaults; malformed/unknown/oversized config fails startup with a safe
localized error. Credentials are forbidden in settings. CLI locale overrides the
stored locale for that invocation only. Configuration loading is bounded to 64 KiB.

The native secret backend is selected on first credential use: Windows credential
store, macOS Keychain or Linux Secret Service. An absent/unavailable backend raises
a stable error without selecting plaintext storage. Unit fakes certify boundary
behavior only; real OS-store integration remains a separate acceptance check.

## Verification

From the installed environment:

```sh
python -m ruff check .
python -m mypy
python -m pytest
python -m build
python scripts/check_wheel.py
```

The CI matrix runs Python 3.12/3.13/3.14 on Windows/Linux/macOS. Building the wheel
and starting it outside the checkout verifies that translation resources and the
entry point are packaged. CI has not run until an actual hosted result exists.

Behavior tests use unittest-compatible classes and are also collected by pytest.
When only a runtime plus Pydantic is available, a narrower offline check is possible
using a source import path and stdlib runner:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m unittest discover -s tests -v
```

This fallback does not establish a successful dependency install, lint/type check,
wheel build, native credential backend or all-OS compatibility. Record such checks
as pending; do not call the entire phase complete based only on this subset.

## Offline interoperability utilities

`python -m ufm --catalog` prints the bundled generic material suggestions as JSON.
`python -m ufm --qr-label UUID` prints a standard QR SVG for `UFM:SPOOL:<uuid>`.
`python -m ufm --spoolman-preview inventory.json --source-instance local-spoolman`
prints a review-only JSON normalization of an explicit Spoolman v1 spool-list file.
These modes do not create application directories, contact printers, mount spools
or change balances. `--locale` selects localized help/errors; JSON keys stay stable.
No camera scanner, committed import or print dialog is provided yet.

## Logging contract

Use stable event identifiers such as `printer_connected`, and allowlisted fields:

```python
logger.info("printer_connected", extra={"fields": {"printer_id": str(printer_id)}})
```

Raw messages, exceptions/tracebacks, unknown field names and URLs are omitted from
output. Console and rotating files share sanitization. Register known opaque secrets
with the shared redaction filter before adapters start; secret patterns alone cannot
recognize arbitrary unknown credential strings. Never submit a raw vendor payload
as logging metadata. Logs are diagnostic, not a replacement for the future durable
inventory audit. If translation resources are unusable, startup emits a stable
`localization_unavailable` diagnostic rather than attempting to echo broken content.

Library references consulted: [Pydantic configuration](https://docs.pydantic.dev/latest/api/config/),
[keyring documentation](https://keyring.readthedocs.io/en/latest/).
