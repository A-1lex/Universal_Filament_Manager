# Threat model — Universal Filament Manager (UFM Studio)

Builds on the repository's own security model: `SECURITY_AND_RESILIENCE.md` (§1 assets/attackers, §2 risks, §4 auth, §8 logging), plus `ARCHITECTURE.md`. Facts marked *(user)* come from those files or from the user; everything else is inferred from code and is subject to confirmation.

## 1. System overview and trust boundaries

UFM Studio is a **single-user, local desktop application** (Python 3.12, Tkinter/PySide6, SQLite) for filament inventory and print accounting, primarily on Windows. *(user: ARCHITECTURE.md, README)* End-user operation needs no browser, Docker or running servers. The repo also vendors a modified copy of **HaspelSync** (`linked-stack/haspelsync`), a Node/Express service with a web UI that syncs a Bambu AMS with Spoolman; UFM can talk to it over HTTP as an optional "accounting authority".

Trust boundaries:
1. **Local user / OS ↔ UFM process** — desktop v1 trusts the local OS account; no app password. *(user: §4)*
2. **UFM ↔ LAN printers** — Bambu LAN MQTT over TLS (pinned cert fingerprint, `bambu_lan.py`), Bambu FTPS, OctoPrint / Moonraker HTTP (`local_http.py`), LAN discovery (`discovery.py`, `bambu_discovery.py`). §1 lists "malicious LAN device" and "compromised printer", but the user has since stated the LAN is trusted (see §7).
3. **UFM ↔ files the user opens** — 3MF/G-code archives (`sliced_files.py`, `gcode_extrusion.py`), Spoolman SQLite import (`integrations/spoolman/importer.py`), HaspelSync config import, Bambu Studio profile files.
4. **UFM ↔ Node calculation worker** — `calculation_worker.py` spawns bundled `node.exe` (or `node` from PATH) running `haspel_worker.mjs` over stdin/stdout JSON.
5. **UFM ↔ HaspelSync service** — `integrations/haspelsync/authority_client.py` (private-address endpoint validation, redirect refusal).
6. **HaspelSync web UI/API ↔ network** — `backend.js` binds `0.0.0.0:4000`; `src/security.js` host/origin guard; `src/auth.js` optional password + API keys (off unless a password is set).
7. **Build/release pipeline** — `scripts/*.ps1` (PyInstaller, Inno Setup, signing, SBOM), `.github/workflows/ci.yml`, HaspelSync Docker publish workflow.

## 2. Components

| Component | Code |
|---|---|
| **Studio Desktop** | `src/ufm/ui/`, `src/ufm/infrastructure/studio_backend.py`, `src/ufm/bootstrap/` |
| **Accounting Core** | `src/ufm/domain/`, `src/ufm/application/`, `src/ufm/infrastructure/persistence/`, `src/ufm/infrastructure/backup/` |
| **Printer Integrations** | `src/ufm/integrations/printers/` |
| **Slice & Calculation** | `src/ufm/integrations/sliced_files.py`, `gcode_extrusion.py`, `slice_artifact_store.py`, `calculation_worker.py`, `haspel_calculation.py`, `haspel_worker.mjs`, `haspel_engine/` |
| **Import & Interop** | `src/ufm/integrations/spoolman/`, `src/ufm/integrations/haspelsync/`, `src/ufm/integrations/catalog/`, `src/ufm/integrations/qr/` |
| **Secrets & Diagnostics** | `src/ufm/infrastructure/secrets/`, `src/ufm/infrastructure/logging/`, `src/ufm/infrastructure/diagnostics.py`, `src/ufm/platform/` |
| **HaspelSync Service** | `linked-stack/haspelsync/` (backend.js, src/, public/, docker/) |
| **Build & Release** | `scripts/`, `.github/`, `experiments/` |

## 3. Entry points and who can reach them

- Desktop UI actions — local user only.
- Files opened/imported by the user (3MF, G-code, Spoolman DB, configs) — content may come from the internet (shared models/projects).
- Printer reports (MQTT JSON, HTTP JSON, FTPS listings/files) — any device that is, or impersonates, a configured printer on the LAN.
- LAN discovery responses (SSDP/UDP, HTTP probes) — any LAN device.
- HaspelSync HTTP API (`src/routes.js`, ~50 routes incl. settings, printers, API keys, restart, diagnostics, log download) — anyone who can reach port 4000; unauthenticated by default unless `AUTH_PASSWORD` set; browser-borne CSRF/DNS-rebinding mitigated by `hostGuard`/`isFromOwnUi`.
- Node worker stdin/stdout — parent process only.

## 4. Assets and sensitivity

*(user: §1)* printer access codes, API tokens, cloud credentials, local inventory/ledger data, print history, customer/project data, plugin/update trust, backups.
Additional: **integrity of the stock ledger** (no double consumption, immutable history — core rule in README); Windows release artifacts and signing material.

## 5. Attacker profiles

*(user: §1)* malicious LAN device; compromised printer/cloud account; malformed 3MF/G-code; malicious plugin; poisoned update; local malware; plus non-adversarial failure sources (accidental user action, DB corruption, duplicate events, races, clock drift, network partitions).
Inferred: a malicious web page in the user's browser targeting HaspelSync on localhost/LAN (CSRF, DNS rebinding).

## 6. Existing controls

- Secrets in OS credential store only, explicit backend class, no plaintext fallback (`infrastructure/secrets/os_store.py`). *(user: §2.6)*
- Bambu MQTT TLS with SHA-256 certificate pinning; autofill requires explicit fingerprint confirmation.
- Local URL validation and redirect refusal for printer HTTP and HaspelSync client (`_validate_local_url`, `_validate_endpoint`, `_private_address`).
- 3MF limits: archive size, entry count, declared size, compression ratio, `..`/absolute path rejection, metadata/G-code size caps (`sliced_files.py`). *(user: §2.8)*
- Bounded worker wire size; worker run without shell.
- Spoolman import previews and backs up source; DB snapshots before import.
- HaspelSync: host allow-list + same-origin guard on writes, optional password with signed cookie, hashed API keys, login rate limiting.
- Stock mutations only via `InventoryCommands`; transactional finalization, idempotency keys. *(user: §2.1–2.2)*
- Plugin loading disabled until sandboxed. *(user: §2.10)*

## 7. Out of scope / accepted risk

*(user: §4)* Local OS trust for desktop v1 — an attacker already running as the user (local malware) is largely accepted; no app password.
*(user: §2.10)* Untrusted plugin execution — not implemented, disabled.
*(user, 2026-11-16)* **HaspelSync (`linked-stack/haspelsync`) is only a reference copy**, not deployed; findings that only affect the HaspelSync Service component get lower priority.
*(user, 2026-11-16)* **The LAN is trusted.** Attacks that require a malicious LAN device, LAN-side MITM, or a compromised/impersonated printer on the LAN are accepted risk.
*(user, 2026-11-16)* **`scripts/`, `.github/` and `experiments/` are out of scope** (Build & Release component); findings only there get lower priority.

## 8. User priorities

*(user, 2026-11-16)* All of these assets are equally critical: printer access codes and tokens; stock-ledger integrity (no double consumption, immutable history); trust in Windows installer builds/updates (runtime update verification in the app).

## 9. Open questions

- No separate infrastructure repository; HaspelSync Docker/Compose files in `linked-stack/haspelsync/docker/` are the only deployment config (reference only).
