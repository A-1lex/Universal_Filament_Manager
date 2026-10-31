# Migration, backup and recovery strategy

Normative design contract, not a claim that every recovery gate is implemented.
Alembic revision `0001_initial` now exists as frozen packaged SQL. The implemented
paths are empty-to-v1 and validated v1 no-op; unknown/newer schemas are rejected.
Database-only verified snapshots exist, but full asset/config backup bundles,
disk-budget checks and upgrades of existing released schemas remain open. See
[implementation status](../IMPLEMENTATION_STATUS.md) for execution evidence.

1. Each schema revision has one immutable Alembic revision ID and a reviewed
   migration. Maintain a linear migration head initially. Never edit a released
   revision or use `create_all` as an upgrade strategy.
2. Startup reads application/schema compatibility before opening write services.
   Reject newer unsupported schemas without modification. A fresh install can
   create v1; an existing unknown/unversioned DB enters recovery, never reset.
3. Stop monitors/writers and acquire the application migration lock. A live SQLite
   database resides on a local filesystem, not a synchronized folder or network
   share. Detect obvious unsupported paths and document detection limitations.
4. Before upgrading an existing DB, create a consistent SQLite online backup and
   an asset/config manifest. Hash all files, verify a restore copy with
   integrity_check and foreign_key_check, and check free-space budget. A failed
   backup blocks migration. The first empty DB has no prior user data to back up.
5. Apply migration with explicit transaction handling compatible with the selected
   SQLite driver. Use Alembic batch operations when rebuilding constrained tables.
   Prove rollback behavior with process-crash tests rather than assuming all DDL
   is transactional. Do not disable FK validation without a controlled rebuild
   and a final full foreign_key_check before application writers resume.
6. Validate row counts, IDs, ledger sums and sequences, active mount uniqueness,
   reservation totals, immutable history and schema version after upgrade. Restore
   indexes/triggers after table rebuild. Preserve NULL and all exact quantities.
7. Only a verified latest schema re-enables application writes. A migration failure
   preserves the original/failed DB and last good backup and opens recovery mode.
   Do not automatically overwrite newer files. Restore into a separate verified
   target, with writers stopped, before an explicit switch to that target.
8. Rollback means restoring a verified pre-upgrade snapshot with a compatible app,
   unless an explicitly tested reversible migration is supplied. Never promise a
   lossless downgrade after new-schema user writes. Retain the newer DB for recovery.

Every released version v1..vN has a fixture containing meaningful data, not an empty
schema. CI upgrades each directly through the full chain to latest on Windows,
Linux and macOS. Include mounted/unmounted spools, unknown and negative balance,
active/released reservations, terminal/pending jobs, receipts awaiting processing,
finalized decisions, corrections, Unicode names and asset references. Verify
history byte/value preservation where appropriate and all constraints afterward.

Crash injection covers backup manifest creation, snapshot completion, table copy,
table rename, version stamp, post-validation and restore switching. Reopening must
show either a supported coherent version or an explicit recovery requirement;
it may never silently create an empty replacement database.

Future PostgreSQL migrations retain domain invariants using engine-specific DDL.
SQLite partial indexes/triggers are not assumed automatically portable. PostgreSQL
server implementation and cross-device authority require a later design/review gate.
