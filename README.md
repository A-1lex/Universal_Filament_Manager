# Universal Filament Manager

**UFM Studio native preview is available.** Windows executable:
`D:\UFM Studio\UFM Studio.exe`; separate imported inventory:
`D:\UFM Studio Data`. Source launch: `python -m ufm.ui.studio` after installing
`.[desktop]`. The Qt workspace supports material profiles, spools, exact manual
stock operations, history, backup/import, local discovery and printer enrollment.
See the [Ukrainian user guide](docs/STUDIO_USER_GUIDE_UK.md),
[design and automation plan](docs/STUDIO_DESIGN_UK.md), and
[continuation checkpoint](docs/DEVELOPMENT_HANDOFF.md).
Automatic print debits and physical printer controls remain unfinished.

The first atomic single-spool finalization service is now implemented and tested:
persisted terminal receipt/evidence, one complete segment, immutable decision,
ledger/projection, own reservation settlement and audit share one transaction.
Replay, concurrent writers and process crashes are covered. It is deliberately
not connected to a live printer worker yet; estimates/unknown mappings are rejected.
See [automatic accounting status](docs/AUTOMATIC_ACCOUNTING_UK.md).

Cross-platform filament inventory and print accounting, designed first for Bambu
Lab P1S without AMS with manufacturer-neutral domain/application contracts.

Confirmed product target (2026-10-25): one native desktop application combining
Spoolman inventory scenarios, HaspelSync printer/accounting scenarios and UFM's
own core, with no browser, Docker or mandatory standalone inventory service at
runtime. The first PySide6 Studio workspace is implemented; the Tkinter shell
remains available as the earlier interface. Versioned adapter contracts support later extensions. See the
[standalone desktop plan](docs/STANDALONE_DESKTOP_PLAN_UK.md). This is the selected
development target, not a claim that the integrated application is complete.

Current state: foundation and domain contracts are implemented. Phase 2 now has a
33-table SQLite schema, frozen Alembic v1 migration, append-only guards, repositories,
explicit UnitOfWork and verified database snapshots. See the exact checkpoint in
[implementation status](docs/IMPLEMENTATION_STATUS.md). Inventory, topology and
reservation command workflows are partially implemented; their safety gates remain
open. The local Tkinter desktop can search and review spools, add a spool from an
existing material profile, set opening stock, record guarded manual additions or
deductions, and inspect the append-only stock history. It imports a Spoolman SQLite
inventory after previewing and backing up the source, and configures read-only
local OctoPrint, Moonraker, and Bambu LAN monitoring with credentials in the native
OS credential store. On Windows, the Printers tab can explicitly search the
primary private LAN for common OctoPrint, Moonraker, and possible Bambu endpoints;
it only offers candidates and never saves or connects to them automatically.
Configured printers can provide a one-time status snapshot;
the Printers tab groups add, search, status and confirmed removal actions; removing
a connection also deletes its OS-stored credential while preserving print history.
Bambu setup can autofill from the matching local Bambu Studio profile after explicit
certificate-fingerprint confirmation. The UI does not yet run a durable polling worker.
Bambu AMS tray identifiers can
be observed, but are not mapped to spools or converted into remaining mass. This
is not yet the complete PySide6 UI or a HaspelSync replacement. Manual deductions
are not automatic print accounting. Historical print usage is not reconstructed
by the importer. A limited atomic single-spool finalization kernel is implemented;
live automatic Bambu/AMS accounting and reconciliation policies remain unfinished. See
[local printer provider status](docs/PRINTER_PROVIDERS.md).
Current local verification uses Windows / Python 3.12;
Linux/macOS require hosted CI results before runtime support is claimed.

For a local desktop preview, install the project in its Python 3.12 environment and
run `ufm-desktop`. The first import flow accepts a Spoolman SQLite file, shows the
number of spools and known/unknown balances, and writes verified snapshots before
importing current known balances as opening ledger entries. The original database is
left unchanged. This early shell does not start or replace the Docker-based
HaspelSync service.

An isolated offline Spoolman API preview adapter is now available; it does not
import or change stock. See the [GitHub component/reuse review](docs/GITHUB_REUSE_REVIEW.md)
for inspected sources, licensing boundaries, usage and the remaining assembly gates.
Offline `--catalog`, `--qr-label UUID` and `--spoolman-preview PATH --source-instance NAME`
commands expose the pinned material reference, QR SVG generator and JSON preview.
Reused data/dependency notices: [third-party notices](THIRD_PARTY_NOTICES.md).

Start with [architecture review](docs/ARCHITECTURE_REVIEW.md), then the five
source-of-truth documents:

- [ARCHITECTURE](ARCHITECTURE.md)
- [DOMAIN_MODEL](DOMAIN_MODEL.md)
- [SECURITY_AND_RESILIENCE](SECURITY_AND_RESILIENCE.md)
- [RISK_REGISTER](RISK_REGISTER.md)
- [IMPLEMENTATION_PLAN](IMPLEMENTATION_PLAN.md)

Implementation proceeds in the canonical phases, starting with Python 3.12+
repository foundation. Tests run after each completed part. UI follows the tested
inventory, feed, reservation and reconciliation core. Automatic deduction requires
replay, crash, identity, partial-print and actual P1S validation.

Core rules: one active physical mount per spool and slot; immutable stock ledger;
exact mass/money; unknown is not zero; a job is initially finalized once; corrections
append history; an accepted measurement cannot double-count unfinalized usage.

SQLite files must remain local, outside active cloud-sync folders and network
shares. Future multi-device use requires an explicit API/server conflict model.
Credentials belong in verified OS secret storage, never DB/config/logs.
