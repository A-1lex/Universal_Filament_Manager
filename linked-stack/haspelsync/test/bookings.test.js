import test, { before, beforeEach, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createServer } from "node:http";
import { spawn } from "node:child_process";

let dir, server, endpoint, journalPath, state, beginBooking, finishBooking, listBookings;
let accountingAuthority, transferAccountingAuthority;
let useSpoolWeight, handlePrintStateChange, flushLogs, requests, mode, used, crashClient;

before(async () => {
    dir = fs.mkdtempSync(path.join(os.tmpdir(), "haspelsync-bookings-"));
    process.env.DATA_DIR = path.join(dir, "printers");
    process.env.LOG_DIR = path.join(dir, "logs");
    fs.mkdirSync(process.env.LOG_DIR, { recursive: true });
    ({ state } = await import("../src/state.js"));
    ({ beginBooking, finishBooking, listBookings } = await import("../src/bookings.js"));
    ({ accountingAuthority, transferAccountingAuthority } = await import("../src/bookings.js"));
    ({ useSpoolWeight } = await import("../src/spoolman.js"));
    ({ handlePrintStateChange } = await import("../src/mqtt.js"));
    ({ flushLogs } = await import("../src/logger.js"));
    ({ bookingsPath: journalPath } = await import("../src/config.js"));
    server = createServer(async (req, res) => {
        if (req.method === "PUT" && /\/use$/.test(req.url)) {
            requests++;
            let raw = "";
            for await (const chunk of req) raw += chunk;
            if (mode === "503") { res.writeHead(503).end(); return; }
            const { use_weight: grams } = JSON.parse(raw);
            used += grams;
            if (mode === "drop") { req.socket.destroy(); return; }
            if (mode === "crash") { crashClient.kill("SIGKILL"); req.socket.destroy(); return; }
            const id = Number(req.url.split("/").at(-2));
            res.setHeader("Content-Type", "application/json");
            res.end(JSON.stringify({ id, remaining_weight: 1000 - used, filament: { name: "PLA", material: "PLA", vendor: { name: "Test" } } }));
        } else {
            res.setHeader("Content-Type", "application/json");
            res.end("{}");
        }
    });
    await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
    endpoint = `http://127.0.0.1:${server.address().port}`;
    const { updateSettings } = await import("../src/settings.js");
    updateSettings({ SPOOLMAN_ENDPOINT: endpoint });
});

beforeEach(() => {
    state.bookingJournal = null;
    fs.rmSync(journalPath, { force: true });
    fs.rmSync(`${journalPath}.lock`, { force: true });
    requests = 0;
    used = 0;
    mode = "success";
});

after(async () => {
    await new Promise(resolve => server.close(resolve));
    await flushLogs();
    fs.rmSync(dir, { recursive: true, force: true });
});

/** A stable physical print occurrence, independent of a completion message. */
function identity(overrides = {}) {
    return { printerId: "TEST-PRINTER", startedAt: 1792800000000, itemKey: "filament0", jobName: "Cube", terminalState: "FINISH", ...overrides };
}

/** Reloads the persisted file as a restarted service would. */
function reload() {
    state.bookingJournal = null;
    return listBookings("TEST-PRINTER");
}

test("revisioned UFM owner transfer blocks Haspel stock consumption on this service", async () => {
    assert.equal(accountingAuthority("TEST-PRINTER").owner, "LEGACY_ACTIVE");
    const requestId = "00000000-0000-4000-8000-000000000001";
    const transferred = transferAccountingAuthority("TEST-PRINTER", {
        owner: "UFM_ACTIVE", expectedRevision: 0, requestId,
    });
    assert.equal(transferred.owner, "UFM_ACTIVE");
    assert.equal(transferred.revision, 1);

    // The actual booking path must stop before making the non-idempotent HTTP write.
    await assert.rejects(
        useSpoolWeight(5, 10, new Date().toISOString(), identity()),
        /booking.owner_not_legacy/,
    );
    assert.equal(requests, 0);

    // Exact retry is idempotent; reusing its ID for a different transition conflicts.
    assert.equal(transferAccountingAuthority("TEST-PRINTER", {
        owner: "UFM_ACTIVE", expectedRevision: 0, requestId,
    }).revision, 1);
    assert.throws(() => transferAccountingAuthority("TEST-PRINTER", {
        owner: "REVIEW_ONLY", expectedRevision: 1, requestId,
    }), /accounting.authority_conflict/);
    assert.equal(accountingAuthority("TEST-PRINTER").owner, "UFM_ACTIVE");
});

test("a stale process cache cannot book after another process transfers the durable owner", async () => {
    assert.equal(accountingAuthority("TEST-PRINTER").owner, "LEGACY_ACTIVE");
    const staleProcessCache = structuredClone(state.bookingJournal);

    // Simulate the second process loading and persisting the shared journal.
    state.bookingJournal = null;
    transferAccountingAuthority("TEST-PRINTER", {
        owner: "UFM_ACTIVE", expectedRevision: 0,
        requestId: "00000000-0000-4000-8000-000000000005",
    });

    // The first, long-lived process still has LEGACY_ACTIVE in memory.
    state.bookingJournal = staleProcessCache;
    await assert.rejects(
        useSpoolWeight(5, 10, new Date().toISOString(), identity()),
        /booking.owner_not_legacy/,
    );
    assert.equal(requests, 0);
    assert.equal(accountingAuthority("TEST-PRINTER").owner, "UFM_ACTIVE");
});

test("an occupied shared journal lock blocks debit and authority transfer", async () => {
    fs.mkdirSync(path.dirname(journalPath), { recursive: true });
    fs.writeFileSync(`${journalPath}.lock`, "another process owns the journal\n");

    await assert.rejects(
        useSpoolWeight(5, 10, new Date().toISOString(), identity()),
        /booking.journal_busy/,
    );
    assert.equal(requests, 0);
    assert.throws(() => transferAccountingAuthority("TEST-PRINTER", {
        owner: "UFM_ACTIVE", expectedRevision: 0,
        requestId: "00000000-0000-4000-8000-000000000006",
    }), /accounting.authority_busy/);
    assert.equal(accountingAuthority("TEST-PRINTER").owner, "LEGACY_ACTIVE");
});

test("unresolved booking intent and stale authority revision prevent UFM activation", () => {
    beginBooking({ ...identity(), spoolId: 5, grams: 10, endpoint });
    assert.throws(() => transferAccountingAuthority("TEST-PRINTER", {
        owner: "UFM_ACTIVE", expectedRevision: 0,
        requestId: "00000000-0000-4000-8000-000000000002",
    }), /accounting.authority_review_required/);
    assert.equal(accountingAuthority("TEST-PRINTER").owner, "LEGACY_ACTIVE");

    assert.equal(transferAccountingAuthority("TEST-PRINTER", {
        owner: "REVIEW_ONLY", expectedRevision: 0,
        requestId: "00000000-0000-4000-8000-000000000003",
    }).revision, 1);
    assert.throws(() => transferAccountingAuthority("TEST-PRINTER", {
        owner: "LEGACY_ACTIVE", expectedRevision: 0,
        requestId: "00000000-0000-4000-8000-000000000004",
    }), /accounting.authority_conflict/);
    assert.equal(accountingAuthority("TEST-PRINTER").owner, "REVIEW_ONLY");
});

test("replayed completion after reloading returns the original result without another debit", async () => {
    const first = await useSpoolWeight(5, 12.34, new Date().toISOString(), identity());
    assert.equal(first.remaining_weight, 987.66);
    assert.equal(reload()[0].status, "booked");
    const again = await useSpoolWeight(5, 12.34, new Date().toISOString(), identity());
    assert.equal(again.remaining_weight, first.remaining_weight);
    assert.equal(requests, 1);
    assert.equal(used, 12.34);
});

test("a dropped response after committing mass is not retried, including after reload", async () => {
    mode = "drop";
    await assert.rejects(useSpoolWeight(5, 12.34, new Date().toISOString(), identity()));
    assert.equal(requests, 1);
    assert.equal(used, 12.34);
    assert.equal(reload()[0].status, "uncertain");
    await assert.rejects(useSpoolWeight(5, 12.34, new Date().toISOString(), identity()), /booking.review_required/);
    assert.equal(requests, 1);
});

test("a 503 response is not automatically repeated by the HTTP client", async () => {
    mode = "503";
    await assert.rejects(useSpoolWeight(5, 10, new Date().toISOString(), identity()));
    assert.equal(requests, 1);
    assert.equal(used, 0);
    assert.equal(reload()[0].status, "uncertain");
});

test("the same sliced file printed again is a new occurrence", async () => {
    await useSpoolWeight(5, 10, new Date().toISOString(), identity());
    await useSpoolWeight(5, 10, new Date().toISOString(), identity({ startedAt: 1792800001000 }));
    assert.equal(requests, 2);
    assert.equal(used, 20);
    assert.equal(reload().length, 2);
});

test("changed amount or physical spool under the same occurrence fails before HTTP", async () => {
    await useSpoolWeight(5, 10, new Date().toISOString(), identity());
    await assert.rejects(useSpoolWeight(5, 11, new Date().toISOString(), identity()), /booking.request_conflict/);
    await assert.rejects(useSpoolWeight(6, 10, new Date().toISOString(), identity()), /booking.request_conflict/);
    assert.equal(requests, 1);
});

test("a pending attempt from a process that exited before sending requires review", async () => {
    beginBooking({ ...identity(), spoolId: 5, grams: 10, endpoint });
    assert.equal(reload()[0].status, "pending");
    await assert.rejects(useSpoolWeight(5, 10, new Date().toISOString(), identity()), /booking.review_required/);
    assert.equal(requests, 0);
});

test("a damaged journal cannot be treated as an empty history", async () => {
    fs.mkdirSync(path.dirname(journalPath), { recursive: true });
    fs.writeFileSync(journalPath, "{broken");
    await assert.rejects(useSpoolWeight(5, 10, new Date().toISOString(), identity()), /booking.journal_unavailable/);
    assert.equal(requests, 0);
});

test("an unreadable journal path blocks the network write", async () => {
    fs.mkdirSync(journalPath, { recursive: true });
    try {
        await assert.rejects(useSpoolWeight(5, 10, new Date().toISOString(), identity()), /booking.journal_unavailable/);
        assert.equal(requests, 0);
    } finally {
        fs.rmdirSync(journalPath);
    }
});

test("missing run identity cannot authorize consumption", async () => {
    await assert.rejects(useSpoolWeight(5, 10, new Date().toISOString(), identity({ startedAt: null })), /booking.identity_invalid/);
    assert.equal(requests, 0);
});

test("journal projections isolate printers and do not expose endpoint credentials", () => {
    const attempt = beginBooking({ ...identity(), spoolId: 5, grams: 10, endpoint: "http://private:secret@example.test" });
    finishBooking(attempt.record.id, "uncertain");
    const stored = fs.readFileSync(journalPath, "utf8");
    assert.ok(!stored.includes("secret"));
    assert.ok(!JSON.stringify(listBookings("TEST-PRINTER")).includes("requestHash"));
    assert.deepEqual(listBookings("OTHER-PRINTER"), []);
});

/** The minimum runtime state for exercising the actual terminal-event handler. */
function terminalPrinter(filaments, spools) {
    return {
        id: "TEST-PRINTER", name: "Test", logFilePath: path.join(process.env.LOG_DIR, "printer.log"),
        currentGcodeState: "RUNNING", currentJobName: "Cube", printStartedAt: 1792800000000,
        currentSliceInfo: { filaments, totalLayers: 10 }, spoolData: spools,
        currentLayerNum: 10, sliceFetchDone: true, stateSeenSinceStart: true,
        currentMapping: null, refills: [],
    };
}

/** An explicitly tag-linked physical spool used by the matching pipeline. */
function slot(label, id, color = "000000") {
    return {
        amsId: label, connectedViaTag: true, existingSpool: { id },
        slot: { tray_info_idx: "GFA00", tray_type: "PLA", tray_color: color, cols: [color] },
    };
}

test("two indistinguishable spools are left uncharged by the real completion handler", async () => {
    // An out-of-range sliced index gives no trustworthy slot position, leaving
    // both tag-linked black spools as candidates in the fallback matching stage.
    const printer = terminalPrinter(
        [{ index: 9, tray_info_idx: "GFA00", type: "PLA", color: "000000", used_g: 10 }],
        [slot("A1", 5), slot("A2", 6)],
    );
    await handlePrintStateChange(printer, { gcode_state: "FINISH", subtask_name: "Cube", layer_num: 10 });
    assert.equal(requests, 0);
    assert.equal(printer.lastPrintSummary.rows[0].status, "skipped");
    assert.match(printer.lastPrintSummary.rows[0].note, /Multiple spools/);
});

test("one unresolved used filament blocks the otherwise known allocations too", async () => {
    const printer = terminalPrinter([
        { index: 0, tray_info_idx: "GFA00", type: "PLA", color: "000000", used_g: 10 },
        { index: 9, tray_info_idx: "OTHER", type: "PETG", color: "FFFFFF", used_g: 5 },
    ], [slot("A1", 5)]);
    await handlePrintStateChange(printer, { gcode_state: "FINISH", subtask_name: "Cube", layer_num: 10 });
    assert.equal(requests, 0);
    assert.ok(printer.lastPrintSummary.rows.every(row => row.status === "skipped"));
});

test("a known external spool is booked and a repeated terminal message has no effect", async () => {
    const printer = terminalPrinter(
        [{ index: 0, tray_info_idx: "GFA00", type: "PLA", color: "000000", used_g: 10 }],
        [slot("External", 5)],
    );
    await handlePrintStateChange(printer, { gcode_state: "FINISH", subtask_name: "Cube", layer_num: 10 });
    assert.equal(printer.lastPrintSummary.rows[0].status, "booked");
    assert.equal(reload()[0].spoolId, 5);
    await handlePrintStateChange(printer, { gcode_state: "FINISH", subtask_name: "Cube", layer_num: 10 });
    assert.equal(requests, 1);
});

test("process termination after a remote debit leaves a pending record that blocks replay", async () => {
    mode = "crash";
    const source = `
        import { useSpoolWeight } from './src/spoolman.js';
        await useSpoolWeight(5, 10, new Date().toISOString(), ${JSON.stringify(identity())});
    `;
    crashClient = spawn(process.execPath, ["--input-type=module", "-e", source], {
        cwd: path.resolve(import.meta.dirname, ".."), env: { ...process.env, NODE_TEST_CONTEXT: "child" },
        windowsHide: true, stdio: "ignore",
    });
    await new Promise((resolve, reject) => {
        const timer = setTimeout(() => { crashClient.kill("SIGKILL"); reject(new Error("worker did not reach the request")); }, 10000);
        crashClient.once("error", error => { clearTimeout(timer); reject(error); });
        crashClient.once("exit", () => { clearTimeout(timer); resolve(); });
    });
    assert.equal(requests, 1);
    assert.equal(used, 10);
    assert.equal(reload()[0].status, "pending");
    mode = "success";
    await assert.rejects(useSpoolWeight(5, 10, new Date().toISOString(), identity()), /booking.review_required/);
    assert.equal(requests, 1);
});
