import test, { before, beforeEach, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { createServer } from "node:http";
import { startTestApp, call } from "./helpers/app.js";

let app, server, endpoint, state, storePath, bookingsPath, printers;
let decimalUnits, snapshotCost, consumptionReport, beginBooking, finishBooking;
let usedWeight, patchCount, mode;

before(async () => {
    app = await startTestApp({ seedPrinters: [{ id: "TEST", name: "Test", ip: "127.0.0.1", code: "test-only" }] });
    ({ state } = await import("../src/state.js"));
    ({ printers } = await import("../src/printers.js"));
    ({ accountingPath: storePath, bookingsPath } = await import("../src/config.js"));
    ({ decimalUnits, snapshotCost, consumptionReport } = await import("../src/accounting.js"));
    ({ beginBooking, finishBooking } = await import("../src/bookings.js"));
    server = createServer(async (req, res) => {
        if (req.method === "PATCH") {
            patchCount++;
            let raw = "";
            for await (const chunk of req) raw += chunk;
            usedWeight = 1000 - JSON.parse(raw).remaining_weight;
            if (mode === "drop") { req.socket.destroy(); return; }
        }
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify({ id: 5, used_weight: usedWeight, remaining_weight: 1000 - usedWeight,
            initial_weight: 1000, spool_weight: 200, filament: { name: "PLA", weight: 1000 } }));
    });
    await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
    endpoint = `http://127.0.0.1:${server.address().port}`;
    const { updateSettings } = await import("../src/settings.js");
    updateSettings({ SPOOLMAN_ENDPOINT: endpoint });
});

beforeEach(() => {
    state.accountingStore = null;
    state.bookingJournal = null;
    for (const file of [storePath, bookingsPath]) fs.rmSync(file, { force: true });
    usedWeight = 400;
    patchCount = 0;
    mode = "success";
    printers[0].currentGcodeState = "IDLE";
    printers[0].spoolData = [{ existingSpool: { id: 5 } }];
});

after(async () => {
    await new Promise(resolve => server.close(resolve));
    await app.close();
});

/** A user-confirmed scale reading based on the balance displayed when the form opened. */
function reading(overrides = {}) {
    return { requestId: randomUUID(), grossGrams: "700,125", tareGrams: "200", expectedUsedWeight: 400, ...overrides };
}

test("decimal commas are exact and scientific, negative or overprecise input is rejected", () => {
    assert.equal(decimalUnits("0,001", 3), 1);
    assert.equal(decimalUnits("999.99", 2), 99999);
    for (const value of ["1e3", "-1", "NaN", "1.0001", "", 0.5]) {
        assert.throws(() => decimalUnits(value, 3), /accountingInvalid/);
    }
});

test("saving prices uses revision checks and snapshots cost without changing earlier bookings", async () => {
    let result = await call(`${app.url}/api/accounting/cost/5`, "PUT", {
        price: "1000", basisGrams: "1000", currency: "UAH", expectedRevision: 0,
    });
    assert.equal(result.status, 200);
    const attempt = beginBooking({ printerId: "TEST", startedAt: 1792800000000, itemKey: "filament0",
        spoolId: 5, grams: 2.345, endpoint, terminalState: "FINISH" });
    assert.equal(attempt.record.cost.costMinor, 235);
    finishBooking(attempt.record.id, "booked", { id: 5 });
    result = await call(`${app.url}/api/accounting/cost/5`, "PUT", {
        price: "2000", basisGrams: "1000", currency: "UAH", expectedRevision: 1,
    });
    assert.equal(result.status, 200);
    assert.equal(snapshotCost(endpoint, 5, 2.345).costMinor, 469);
    const report = await call(`${app.url}/api/print/TEST/report`);
    assert.equal(report.body.totals[0].costMinor, 235);
    result = await call(`${app.url}/api/accounting/cost/5`, "PUT", {
        price: "1", basisGrams: "1000", currency: "USD", expectedRevision: 1,
    });
    assert.equal(result.status, 409);
});

test("prices are scoped to a Spoolman instance, not a naked numeric spool id", async () => {
    await call(`${app.url}/api/accounting/cost/5`, "PUT", { price: "500", basisGrams: "1000", currency: "UAH", expectedRevision: 0 });
    assert.equal(snapshotCost("http://different-instance", 5, 10), null);
});

test("reports separate currencies, exclude uncertain amounts and expose missing prices", () => {
    const report = consumptionReport([
        { startedAt: 100, status: "booked", grams: 10, cost: { currency: "UAH", costMinor: 100 } },
        { startedAt: 100, status: "booked", grams: 20, cost: { currency: "EUR", costMinor: 50 } },
        { startedAt: 200, status: "uncertain", grams: 100, cost: { currency: "UAH", costMinor: 5000 } },
        { startedAt: 300, status: "booked", grams: 5, cost: null },
    ], 100, 301);
    assert.equal(report.grams, 35);
    assert.equal(report.printCount, 3);
    assert.equal(report.reviewCount, 1);
    assert.equal(report.unknownCostCount, 1);
    assert.deepEqual(report.totals, [{ currency: "UAH", costMinor: 100 }, { currency: "EUR", costMinor: 50 }]);
});

test("gross-minus-tare applies once, persists and replays without another patch", async () => {
    const payload = reading();
    let result = await call(`${app.url}/api/accounting/weigh/5`, "POST", payload);
    assert.equal(result.status, 200);
    assert.equal(result.body.record.netMilligrams, 500125);
    assert.equal(usedWeight, 499.875);
    state.accountingStore = null;
    result = await call(`${app.url}/api/accounting/weigh/5`, "POST", payload);
    assert.equal(result.status, 200);
    assert.equal(patchCount, 1);
    const view = await call(`${app.url}/api/accounting`);
    assert.equal(view.body.weighings[0].status, "recorded");
});

test("an older balance cannot overwrite later consumption", async () => {
    const result = await call(`${app.url}/api/accounting/weigh/5`, "POST", reading({ expectedUsedWeight: 399 }));
    assert.equal(result.status, 409);
    assert.equal(patchCount, 0);
    assert.equal(usedWeight, 400);
});

test("tare above gross and mass above the spool capacity are rejected without a stock write", async () => {
    let result = await call(`${app.url}/api/accounting/weigh/5`, "POST", reading({ grossGrams: "100" }));
    assert.equal(result.status, 400);
    result = await call(`${app.url}/api/accounting/weigh/5`, "POST", reading({ grossGrams: "1300" }));
    assert.equal(result.status, 409);
    assert.equal(patchCount, 0);
});

test("a running print or an uncertain debit blocks independent weighing", async () => {
    printers[0].currentGcodeState = "RUNNING";
    let result = await call(`${app.url}/api/accounting/weigh/5`, "POST", reading());
    assert.equal(result.status, 409);
    printers[0].currentGcodeState = "IDLE";
    beginBooking({ printerId: "TEST", startedAt: 1792800000000, itemKey: "filament0",
        spoolId: 5, grams: 10, endpoint, terminalState: "FINISH" });
    result = await call(`${app.url}/api/accounting/weigh/5`, "POST", reading());
    assert.equal(result.status, 409);
    assert.equal(patchCount, 0);
});

test("an acknowledged correction with a lost response is journaled and never resent", async () => {
    mode = "drop";
    const payload = reading();
    let result = await call(`${app.url}/api/accounting/weigh/5`, "POST", payload);
    assert.equal(result.status, 503);
    assert.equal(patchCount, 1);
    assert.equal(usedWeight, 499.875);
    state.accountingStore = null;
    result = await call(`${app.url}/api/accounting/weigh/5`, "POST", payload);
    assert.equal(result.status, 409);
    assert.equal(patchCount, 1);
    const view = await call(`${app.url}/api/accounting`);
    assert.equal(view.body.weighings[0].status, "uncertain");
});

test("reports and accounting writes require authentication", async () => {
    for (const [route, method, payload] of [
        ["/api/accounting", "GET", undefined],
        ["/api/print/TEST/report", "GET", undefined],
        ["/api/accounting/cost/5", "PUT", {}],
        ["/api/accounting/weigh/5", "POST", reading()],
    ]) {
        const result = await call(app.url + route, method, payload, {});
        assert.equal(result.status, 401);
    }
});

test("an explicit review resolves an uncertain debit without any stock mutation", async () => {
    const attempt = beginBooking({ printerId: "TEST", startedAt: 1792800000000, itemKey: "filament0",
        spoolId: 5, grams: 10, endpoint, terminalState: "FINISH" });
    finishBooking(attempt.record.id, "uncertain");
    const url = `${app.url}/api/print/TEST/bookings/${attempt.record.id}/resolve`;
    const payload = { resolution: "not_applied", note: "Checked the balance and printer log" };
    let result = await call(url, "POST", payload);
    assert.equal(result.status, 200);
    result = await call(url, "POST", payload);
    assert.equal(result.status, 200);
    assert.equal(usedWeight, 400);
    assert.equal(patchCount, 0);
    const report = await call(`${app.url}/api/print/TEST/report`);
    assert.equal(report.body.bookings[0].status, "dismissed");
    assert.equal(report.body.reviewCount, 0);
    assert.equal(report.body.grams, 0);
});

test("review requires a reason and cannot race a request still in flight", async () => {
    const attempt = beginBooking({ printerId: "TEST", startedAt: 1792800000000, itemKey: "filament0",
        spoolId: 5, grams: 10, endpoint, terminalState: "FINISH" });
    const url = `${app.url}/api/print/TEST/bookings/${attempt.record.id}/resolve`;
    let result = await call(url, "POST", { resolution: "applied", note: " " });
    assert.equal(result.status, 409);
    state.activeBookingIds.add(attempt.record.id);
    result = await call(url, "POST", { resolution: "applied", note: "Verified" });
    assert.equal(result.status, 409);
    state.activeBookingIds.delete(attempt.record.id);
    result = await call(url, "POST", { resolution: "applied", note: "Verified" });
    assert.equal(result.status, 200);
    assert.equal(patchCount, 0);
    const report = await call(`${app.url}/api/print/TEST/report`);
    assert.equal(report.body.grams, 10);
    assert.equal(report.body.bookings[0].resolutionNote, "Verified");
});

test("a lost weighing response can be acknowledged without repeating the correction", async () => {
    mode = "drop";
    const payload = reading();
    await call(`${app.url}/api/accounting/weigh/5`, "POST", payload);
    assert.equal(patchCount, 1);
    const result = await call(`${app.url}/api/accounting/weighings/${payload.requestId}/resolve`, "POST",
        { resolution: "applied", note: "Scale reading and resulting balance agree" });
    assert.equal(result.status, 200);
    assert.equal(patchCount, 1);
    const view = await call(`${app.url}/api/accounting`);
    assert.equal(view.body.weighings[0].status, "recorded");
});

test("an uncertain absolute weighing blocks both another reading and a new consumption write", async () => {
    mode = "drop";
    await call(`${app.url}/api/accounting/weigh/5`, "POST", reading());
    const result = await call(`${app.url}/api/accounting/weigh/5`, "POST", reading({ expectedUsedWeight: usedWeight }));
    assert.equal(result.status, 409);
    assert.equal(patchCount, 1);
    assert.throws(() => beginBooking({ printerId: "TEST", startedAt: 1792800000000, itemKey: "filament0",
        spoolId: 5, grams: 10, endpoint, terminalState: "FINISH" }), /accountingReviewRequired/);
});
