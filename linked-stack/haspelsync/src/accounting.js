import fs from "node:fs";
import { createHash } from "node:crypto";
import { accountingPath } from "./config.js";
import { state } from "./state.js";
import { writeJsonFile } from "./jsonfile.js";

/** Hashes identities without retaining a credential-bearing Spoolman URL. */
function hash(value) {
    return createHash("sha256").update(JSON.stringify(value)).digest("hex");
}

/** Parses user decimal text into exact minor units, accepting the decimal comma. */
export function decimalUnits(value, places) {
    if (typeof value !== "string" || value.length > 30) throw new Error("accountingInvalid");
    const normalized = value.trim().replace(",", ".");
    if (!new RegExp(`^\\d{1,9}(?:\\.\\d{1,${places}})?$`).test(normalized)) throw new Error("accountingInvalid");
    const [whole, fraction = ""] = normalized.split(".");
    const units = Number(whole) * 10 ** places + Number(fraction.padEnd(places, "0"));
    if (!Number.isSafeInteger(units)) throw new Error("accountingInvalid");
    return units;
}

/** Loads strictly so a damaged price or weighing record cannot authorize a write. */
function load() {
    if (state.accountingStore) return state.accountingStore;
    try {
        if (fs.statSync(accountingPath).size > 16 * 1024 * 1024) throw new Error();
        const data = JSON.parse(fs.readFileSync(accountingPath, "utf8"));
        if (data?.schemaVersion !== 1 || !data.profiles || typeof data.profiles !== "object"
            || Array.isArray(data.profiles) || !Array.isArray(data.weighings)
            || data.weighings.length > 10000) throw new Error();
        for (const profile of Object.values(data.profiles)) {
            if (!profile || !Number.isSafeInteger(profile.spoolId) || profile.spoolId <= 0
                || !Number.isSafeInteger(profile.priceMinor) || profile.priceMinor < 0
                || !Number.isSafeInteger(profile.basisMilligrams) || profile.basisMilligrams <= 0
                || !["UAH", "EUR", "USD", "PLN"].includes(profile.currency)
                || !Number.isSafeInteger(profile.revision) || profile.revision < 1
                || !/^[a-f0-9]{64}$/.test(profile.source)) throw new Error();
        }
        for (const record of data.weighings) {
            if (!record || !["pending", "recorded", "uncertain", "rejected"].includes(record.status)
                || typeof record.id !== "string" || !/^[a-f0-9]{64}$/.test(record.requestHash)
                || !/^[a-f0-9]{64}$/.test(record.source)
                || !Number.isSafeInteger(record.spoolId) || record.spoolId <= 0
                || !Number.isSafeInteger(record.netMilligrams) || record.netMilligrams < 0) throw new Error();
        }
        state.accountingStore = data;
    } catch (error) {
        if (error.code !== "ENOENT") throw new Error("accountingUnavailable");
        state.accountingStore = { schemaVersion: 1, profiles: {}, weighings: [] };
    }
    return state.accountingStore;
}

/** Atomically replaces the file before exposing updated state to another caller. */
function persist(data) {
    if (Buffer.byteLength(JSON.stringify(data)) > 16 * 1024 * 1024) throw new Error("accountingUnavailable");
    writeJsonFile(accountingPath, data, { throwOnError: true });
    state.accountingStore = data;
}

/** Returns this Spoolman instance's editable price bases and recent weighings. */
export function accountingView(endpoint) {
    const data = load(), source = hash(endpoint);
    return {
        profiles: Object.values(data.profiles).filter(profile => profile.source === source)
            .map(({ source: _source, ...profile }) => structuredClone(profile)),
        weighings: data.weighings.filter(record => record.source === source).slice(-100).reverse()
            .map(({ source: _source, requestHash: _hash, ...record }) => structuredClone(record)),
    };
}

/** Saves a price for an explicit net mass basis, rejecting a stale browser form. */
export function saveCostProfile(endpoint, spoolId, { price, basisGrams, currency, expectedRevision }) {
    const priceMinor = decimalUnits(price, 2), basisMilligrams = decimalUnits(basisGrams, 3);
    if (!Number.isSafeInteger(spoolId) || spoolId <= 0 || basisMilligrams <= 0
        || !["UAH", "EUR", "USD", "PLN"].includes(currency)
        || !Number.isSafeInteger(expectedRevision) || expectedRevision < 0) throw new Error("accountingInvalid");
    const data = load(), key = hash([endpoint, spoolId]);
    const current = data.profiles[key];
    if ((current?.revision ?? 0) !== expectedRevision) throw new Error("accountingConflict");
    const profile = { spoolId, priceMinor, basisMilligrams, currency, source: hash(endpoint),
        revision: expectedRevision + 1, updatedAt: Date.now() };
    persist({ ...data, profiles: { ...data.profiles, [key]: profile } });
    return accountingView(endpoint);
}

/** Captures filament cost at booking time with integer arithmetic and half-up rounding. */
export function snapshotCost(endpoint, spoolId, grams) {
    const profile = load().profiles[hash([endpoint, spoolId])];
    if (!profile) return null;
    const massMilligrams = Math.round(grams * 1000);
    if (!Number.isSafeInteger(massMilligrams) || massMilligrams < 0
        || Math.abs(grams * 1000 - massMilligrams) > 0.0001) throw new Error("accountingInvalid");
    const numerator = BigInt(profile.priceMinor) * BigInt(massMilligrams);
    const basis = BigInt(profile.basisMilligrams);
    const costMinor = Number((numerator * 2n + basis) / (2n * basis));
    if (!Number.isSafeInteger(costMinor)) throw new Error("accountingInvalid");
    return { currency: profile.currency, costMinor, priceMinor: profile.priceMinor,
        basisMilligrams: profile.basisMilligrams, massMilligrams };
}

/** Prevents a new debit from racing an unfinished or uncertain absolute correction. */
export function hasUncertainWeighing(endpoint, spoolId) {
    const source = hash(endpoint);
    return load().weighings.some(record => record.source === source && record.spoolId === spoolId
        && ["pending", "uncertain"].includes(record.status));
}

/** Records a weighing intent before a remote correction, keeping retries explicit. */
export function beginWeighing(endpoint, spoolId, payload) {
    const { requestId, grossGrams, tareGrams, expectedUsedWeight } = payload;
    if (typeof requestId !== "string" || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(requestId)
        || !Number.isSafeInteger(spoolId) || spoolId <= 0
        || !Number.isFinite(expectedUsedWeight) || expectedUsedWeight < 0) throw new Error("accountingInvalid");
    const grossMilligrams = decimalUnits(grossGrams, 3), tareMilligrams = decimalUnits(tareGrams, 3);
    if (grossMilligrams < tareMilligrams) throw new Error("accountingInvalid");
    const data = load(), source = hash(endpoint);
    const requestHash = hash([source, spoolId, grossMilligrams, tareMilligrams, expectedUsedWeight]);
    const prior = data.weighings.find(record => record.id === requestId);
    if (prior) {
        if (prior.requestHash !== requestHash) throw new Error("accountingConflict");
        return { created: false, record: structuredClone(prior) };
    }
    if (hasUncertainWeighing(endpoint, spoolId)) throw new Error("accountingReviewRequired");
    if (data.weighings.length >= 10000) throw new Error("accountingUnavailable");
    const record = { id: requestId, requestHash, source, spoolId, grossMilligrams, tareMilligrams,
        netMilligrams: grossMilligrams - tareMilligrams, expectedUsedWeight, createdAt: Date.now(), status: "pending" };
    persist({ ...data, weighings: [...data.weighings, record] });
    return { created: true, record: structuredClone(record) };
}

/** Saves a weighing's result without removing the original attempt. */
export function finishWeighing(id, status) {
    const data = load();
    const prior = data.weighings.find(record => record.id === id);
    if (!prior || prior.status !== "pending" || !["recorded", "uncertain", "rejected"].includes(status)) throw new Error("accountingConflict");
    persist({ ...data, weighings: data.weighings.map(record => record.id === id
        ? { ...record, status, completedAt: Date.now() } : record) });
}

/** Confirms an uncertain weighing after a person checks Spoolman; never patches stock. */
export function resolveWeighing(endpoint, id, resolution, note) {
    const data = load(), prior = data.weighings.find(record => record.id === id);
    if (!prior || prior.source !== hash(endpoint) || state.activeWeighingIds.has(id)
        || !["applied", "not_applied"].includes(resolution)
        || typeof note !== "string" || !note.trim() || note.length > 500) throw new Error("accountingConflict");
    if (prior.resolution === resolution && prior.resolutionNote === note.trim()) return;
    if (!["pending", "uncertain"].includes(prior.status)) throw new Error("accountingConflict");
    persist({ ...data, weighings: data.weighings.map(record => record.id === id
        ? { ...record, status: resolution === "applied" ? "recorded" : "rejected",
            resolution, resolutionNote: note.trim(), resolvedAt: Date.now() } : record) });
}

/** Aggregates acknowledged consumption, retaining separate totals for every currency. */
export function consumptionReport(records, from = 0, until = Number.MAX_SAFE_INTEGER) {
    if (!Number.isSafeInteger(from) || !Number.isSafeInteger(until) || from < 0 || until <= from) throw new Error("accountingInvalid");
    const selected = records.filter(record => record.startedAt >= from && record.startedAt < until);
    const booked = selected.filter(record => record.status === "booked");
    const totals = new Map();
    for (const record of booked) {
        if (!record.cost) continue;
        const current = totals.get(record.cost.currency) ?? 0;
        const total = current + record.cost.costMinor;
        if (!Number.isSafeInteger(total)) throw new Error("accountingInvalid");
        totals.set(record.cost.currency, total);
    }
    return {
        bookings: selected, printCount: new Set(selected.map(record => record.startedAt)).size,
        grams: Math.round(booked.reduce((sum, record) => sum + record.grams, 0) * 1000) / 1000,
        reviewCount: selected.filter(record => ["pending", "uncertain"].includes(record.status)).length,
        unknownCostCount: booked.filter(record => !record.cost).length,
        totals: [...totals].map(([currency, costMinor]) => ({ currency, costMinor })),
    };
}
