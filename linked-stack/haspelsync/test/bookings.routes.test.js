import test, { before, beforeEach, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { startTestApp, call } from "./helpers/app.js";

let app, state, beginBooking, finishBooking;

before(async () => {
    app = await startTestApp({ seedPrinters: [
        { id: "TEST-A", name: "Printer A", ip: "127.0.0.1", code: "test-only" },
        { id: "TEST-B", name: "Printer B", ip: "127.0.0.1", code: "test-only" },
    ] });
    ({ state } = await import("../src/state.js"));
    ({ beginBooking, finishBooking } = await import("../src/bookings.js"));
});

beforeEach(() => {
    state.bookingJournal = null;
    fs.rmSync(path.join(app.dataDir, "bookings.json"), { force: true });
});

after(async () => { await app.close(); });

test("the history endpoint requires the same authentication as other printer APIs", async () => {
    const { status } = await call(`${app.url}/api/print/TEST-A/bookings`, "GET", undefined, {});
    assert.equal(status, 401);
});

test("the history endpoint isolates printer records and omits request hashes", async () => {
    for (const printerId of ["TEST-A", "TEST-B"]) {
        const attempt = beginBooking({ printerId, startedAt: 1792800000000, itemKey: "filament0",
            spoolId: printerId === "TEST-A" ? 5 : 6, grams: 10, endpoint: "http://user:private@example.test", terminalState: "FINISH" });
        finishBooking(attempt.record.id, "uncertain");
    }
    const { status, body } = await call(`${app.url}/api/print/TEST-A/bookings`);
    assert.equal(status, 200);
    assert.equal(body.ok, true);
    assert.equal(body.bookings.length, 1);
    assert.equal(body.bookings[0].printerId, "TEST-A");
    assert.equal(body.bookings[0].status, "uncertain");
    assert.ok(!JSON.stringify(body).includes("requestHash"));
    assert.ok(!JSON.stringify(body).includes("private"));
});

test("unknown printers do not expose any journal records", async () => {
    const { status } = await call(`${app.url}/api/print/UNKNOWN/bookings`);
    assert.equal(status, 404);
});

test("a corrupt journal is reported as unavailable instead of an empty success", async () => {
    fs.writeFileSync(path.join(app.dataDir, "bookings.json"), "broken");
    const { status, body } = await call(`${app.url}/api/print/TEST-A/bookings`);
    assert.equal(status, 503);
    assert.equal(body.ok, false);
    assert.equal(body.code, "bookingHistoryUnavailable");
});
