import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import { bookingsPath } from "./config.js";
import { writeJsonFile } from "./jsonfile.js";
import { state } from "./state.js";
import { snapshotCost, hasUncertainWeighing } from "./accounting.js";

const MAX_BYTES = 16 * 1024 * 1024;
const MAX_RECORDS = 10000;
const STATUSES = new Set(["pending", "booked", "uncertain", "dismissed"]);
const AUTHORITY_OWNERS = new Set(["LEGACY_ACTIVE", "UFM_ACTIVE", "REVIEW_ONLY"]);
const REQUEST_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Returns a stable digest without storing an endpoint that may contain credentials. */
function digest(value) {
    return createHash("sha256").update(JSON.stringify(value)).digest("hex");
}

/** Validates a record before it can authorize a replay without an HTTP write. */
function validRecord(key, record) {
    return /^[a-f0-9]{64}$/.test(key) && record && typeof record === "object"
        && record.id === key && /^[a-f0-9]{64}$/.test(record.requestHash)
        && typeof record.printerId === "string" && record.printerId.length > 0
        && typeof record.itemKey === "string" && record.itemKey.length > 0
        && Number.isSafeInteger(record.startedAt) && record.startedAt > 0
        && Number.isSafeInteger(record.spoolId) && record.spoolId > 0
        && Number.isFinite(record.grams) && record.grams > 0
        && STATUSES.has(record.status)
        && Number.isSafeInteger(record.createdAt) && Number.isSafeInteger(record.updatedAt)
        && (record.cost == null || (Number.isSafeInteger(record.cost.costMinor) && record.cost.costMinor >= 0
            && ["UAH", "EUR", "USD", "PLN"].includes(record.cost.currency)))
        && (record.status !== "booked" || record.result?.id === record.spoolId);
}

/** Validates the durable per-printer owner records stored beside booking intents. */
function validAuthority(record) {
    return record && typeof record === "object"
        && AUTHORITY_OWNERS.has(record.owner)
        && Number.isSafeInteger(record.revision) && record.revision >= 1
        && REQUEST_ID.test(record.requestId)
        && /^[a-f0-9]{64}$/.test(record.requestHash)
        && Number.isSafeInteger(record.updatedAt) && record.updatedAt > 0;
}

/** Loads strictly: treating a damaged journal as empty would permit another debit. */
function load({ refresh = false } = {}) {
    if (!refresh && state.bookingJournal) return state.bookingJournal;
    try {
        if (fs.statSync(bookingsPath).size > MAX_BYTES) throw new Error();
        const parsed = JSON.parse(fs.readFileSync(bookingsPath, "utf8"));
        const owners = parsed?.owners ?? {};
        if (parsed?.schemaVersion !== 1 || !parsed.records || Array.isArray(parsed.records)
            || typeof parsed.records !== "object" || Object.keys(parsed.records).length > MAX_RECORDS
            || !Object.entries(parsed.records).every(([key, record]) => validRecord(key, record))
            || !owners || typeof owners !== "object" || Array.isArray(owners)
            || Object.keys(owners).length > MAX_RECORDS
            || !Object.entries(owners).every(([printerId, record]) =>
                printerId.length > 0 && printerId.length <= 200 && validAuthority(record))) {
            throw new Error();
        }
        // Older schemaVersion 1 journals have no owner map. They retain the
        // historical LEGACY_ACTIVE behavior until an explicit transfer.
        state.bookingJournal = { ...parsed, owners };
    } catch (error) {
        if (error.code !== "ENOENT") throw new Error("booking.journal_unavailable");
        state.bookingJournal = { schemaVersion: 1, records: {}, owners: {} };
    }
    return state.bookingJournal;
}

/** Publishes memory only after the atomic file replacement has succeeded. */
function persist(journal) {
    if (Buffer.byteLength(JSON.stringify(journal)) > MAX_BYTES) throw new Error("booking.journal_full");
    writeJsonFile(bookingsPath, journal, { throwOnError: true });
    state.bookingJournal = journal;
}

/**
 * Serializes durable journal read/modify/write transactions across processes
 * that share DATA_DIR. A leftover lock after a process crash is deliberately
 * fail-closed and needs operator review; it is never removed speculatively.
 */
function withJournalLock(operation, busyError) {
    fs.mkdirSync(path.dirname(bookingsPath), { recursive: true });
    const lockPath = `${bookingsPath}.lock`;
    let descriptor;
    try {
        descriptor = fs.openSync(lockPath, "wx", 0o600);
    } catch (error) {
        if (error.code === "EEXIST") throw new Error(busyError);
        throw new Error("booking.journal_unavailable");
    }
    try {
        fs.writeFileSync(descriptor, `${process.pid}\n`);
        state.bookingJournal = null;
        return operation();
    } finally {
        try {
            fs.closeSync(descriptor);
        } finally {
            try {
                fs.unlinkSync(lockPath);
            } catch (error) {
                if (error.code !== "ENOENT") throw error;
            }
        }
    }
}

/**
 * Records intent before a non-idempotent Spoolman request can leave the process.
 * The run and sliced item identify it; changing mass, spool or endpoint conflicts.
 */
export function beginBooking({ printerId, startedAt, itemKey, spoolId, grams, endpoint, jobName = null, terminalState = null }) {
    if (typeof printerId !== "string" || !printerId || printerId.length > 200
        || typeof itemKey !== "string" || !itemKey || itemKey.length > 200
        || !Number.isSafeInteger(startedAt) || startedAt <= 0
        || !Number.isSafeInteger(spoolId) || spoolId <= 0
        || !Number.isFinite(grams) || grams <= 0
        || typeof endpoint !== "string" || !endpoint
        || (jobName !== null && (typeof jobName !== "string" || jobName.length > 500))
        || !["FINISH", "FAILED", "CANCEL"].includes(terminalState)) {
        throw new Error("booking.identity_invalid");
    }
    return withJournalLock(() => {
        // Refresh inside the inter-process lock: another HaspelSync process
        // may have transferred ownership or booked this print occurrence.
        const journal = load({ refresh: true });
        const id = digest([printerId, startedAt, itemKey]);
        const requestHash = digest([endpoint, spoolId, grams, jobName, terminalState]);
        const prior = journal.records[id];
        if (prior) {
            if (prior.requestHash !== requestHash) throw new Error("booking.request_conflict");
            return { created: false, record: structuredClone(prior) };
        }
        if ((journal.owners[printerId]?.owner ?? "LEGACY_ACTIVE") !== "LEGACY_ACTIVE") {
            throw new Error("booking.owner_not_legacy");
        }
        if (hasUncertainWeighing(endpoint, spoolId) || hasUncertainBooking(spoolId)) {
            throw new Error("accountingReviewRequired");
        }
        if (Object.keys(journal.records).length >= MAX_RECORDS) throw new Error("booking.journal_full");
        const now = Date.now();
        const record = {
            id, requestHash, printerId, startedAt, itemKey, spoolId, grams, source: digest(endpoint),
            jobName, terminalState, status: "pending", createdAt: now, updatedAt: now, result: null,
            cost: snapshotCost(endpoint, spoolId, grams),
        };
        persist({ ...journal, records: { ...journal.records, [id]: record } });
        return { created: true, record: structuredClone(record) };
    }, "booking.journal_busy");
}

/** Returns the authority advertised by this HaspelSync service for one printer. */
export function accountingAuthority(printerId) {
    if (typeof printerId !== "string" || !printerId || printerId.length > 200) {
        throw new Error("accounting.authority_invalid");
    }
    const journal = load({ refresh: true });
    const record = journal.owners[printerId];
    const bookings = Object.values(journal.records).filter(item => item.printerId === printerId);
    return {
        capabilityVersion: 1,
        printerId,
        owner: record?.owner ?? "LEGACY_ACTIVE",
        revision: record?.revision ?? 0,
        pendingCount: bookings.filter(item => item.status === "pending").length,
        uncertainCount: bookings.filter(item => item.status === "uncertain").length,
        activeCount: bookings.filter(item => state.activeBookingIds.has(item.id)).length,
    };
}

/**
 * Transfers this service's durable booking owner after pending writes drain.
 * The owner check and booking intent write are synchronous in the same process.
 */
export function transferAccountingAuthority(printerId, { owner, expectedRevision, requestId }) {
    if (typeof printerId !== "string" || !printerId || printerId.length > 200
        || !AUTHORITY_OWNERS.has(owner)
        || !Number.isSafeInteger(expectedRevision) || expectedRevision < 0
        || typeof requestId !== "string" || !REQUEST_ID.test(requestId)) {
        throw new Error("accounting.authority_invalid");
    }
    return withJournalLock(() => {
        const journal = load({ refresh: true });
        const prior = journal.owners[printerId];
        const current = prior?.owner ?? "LEGACY_ACTIVE";
        const revision = prior?.revision ?? 0;
        const requestHash = digest([printerId, expectedRevision, owner]);
        if (prior?.requestId === requestId) {
            if (prior.requestHash !== requestHash) throw new Error("accounting.authority_conflict");
            return accountingAuthority(printerId);
        }
        if (expectedRevision !== revision) throw new Error("accounting.authority_conflict");

        const allowed = {
            LEGACY_ACTIVE: new Set(["UFM_ACTIVE", "REVIEW_ONLY"]),
            UFM_ACTIVE: new Set(["REVIEW_ONLY"]),
            REVIEW_ONLY: new Set(["LEGACY_ACTIVE"]),
        };
        if (!allowed[current].has(owner)) throw new Error("accounting.authority_transition_invalid");

        const bookings = Object.values(journal.records).filter(item => item.printerId === printerId);
        if (bookings.some(item => state.activeBookingIds.has(item.id))) {
            throw new Error("accounting.authority_busy");
        }
        if (owner !== "REVIEW_ONLY" && bookings.some(item => ["pending", "uncertain"].includes(item.status))) {
            throw new Error("accounting.authority_review_required");
        }

        const record = {
            owner,
            revision: revision + 1,
            requestId,
            requestHash,
            updatedAt: Date.now(),
        };
        persist({ ...journal, owners: { ...journal.owners, [printerId]: record } });
        return accountingAuthority(printerId);
    }, "accounting.authority_busy");
}

/**
 * Finishes an attempt without erasing its identity. An uncertain request is never
 * sent again automatically: Spoolman may have committed before the connection broke.
 */
export function finishBooking(id, status, spool = null) {
    return withJournalLock(() => {
        const journal = load({ refresh: true });
        const prior = journal.records[id];
        if (!prior || prior.status !== "pending" || !["booked", "uncertain"].includes(status)) {
            throw new Error("booking.transition_invalid");
        }
        if (status === "booked" && spool?.id !== prior.spoolId) throw new Error("booking.response_invalid");
        const result = status === "booked" ? {
            id: spool.id,
            remaining_weight: Number.isFinite(spool.remaining_weight) ? spool.remaining_weight : null,
            filament: {
                name: spool.filament?.name ?? null,
                material: spool.filament?.material ?? null,
                vendor: { name: spool.filament?.vendor?.name ?? null },
            },
        } : null;
        const record = { ...prior, status, updatedAt: Date.now(), result };
        persist({ ...journal, records: { ...journal.records, [id]: record } });
        return structuredClone(record);
    }, "booking.journal_busy");
}

/** Lists recent attempts for one printer, without hashes or endpoint credentials. */
export function listBookings(printerId, limit = 100) {
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > MAX_RECORDS) throw new Error("booking.limit_invalid");
    return Object.values(load().records)
        .filter(record => record.printerId === printerId)
        .sort((a, b) => b.createdAt - a.createdAt)
        .slice(0, limit)
        .map(({ requestHash: _hash, source: _source, ...record }) => structuredClone(record));
}

/** Blocks weighing while an earlier consumption write may already have affected this spool. */
export function hasUncertainBooking(spoolId) {
    return Object.values(load().records).some(record => record.spoolId === spoolId && ["pending", "uncertain"].includes(record.status));
}

/** Records an explicit human review without sending or repeating a stock mutation. */
export function resolveBooking(id, endpoint, resolution, note, spool) {
    return withJournalLock(() => {
        const journal = load({ refresh: true }), prior = journal.records[id];
        if (!prior || prior.source !== digest(endpoint) || state.activeBookingIds.has(id)
            || !["applied", "not_applied"].includes(resolution)
            || typeof note !== "string" || !note.trim() || note.length > 500) throw new Error("accountingConflict");
        if (prior.resolution === resolution && prior.resolutionNote === note.trim()) return;
        if (!["pending", "uncertain"].includes(prior.status)) throw new Error("accountingConflict");
        if (spool?.id !== prior.spoolId) throw new Error("accountingConflict");
        const record = { ...prior, status: resolution === "applied" ? "booked" : "dismissed",
            resolution, resolutionNote: note.trim(), resolvedAt: Date.now(), updatedAt: Date.now(),
            result: resolution === "applied" ? { id: spool.id, remaining_weight: spool.remaining_weight ?? null,
                filament: { name: spool.filament?.name ?? null, material: spool.filament?.material ?? null,
                    vendor: { name: spool.filament?.vendor?.name ?? null } } } : null };
        persist({ ...journal, records: { ...journal.records, [id]: record } });
    }, "booking.journal_busy");
}
