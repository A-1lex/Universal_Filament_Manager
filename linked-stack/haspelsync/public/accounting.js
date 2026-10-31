import { fetchJson, sendJson, escapeHtml as esc } from "./ui.js";

let inventory = [], profiles = [], weighings = [], report = null, currentSpool = null;
let weighingId = crypto.randomUUID();
let reportGeneration = 0;
let reviewTarget = null;

/** Looks up a page control. */
function control(id) { return document.getElementById(id); }

/** Uses the viewer's locale for mass and money. */
function number(value, digits = 3) {
    return Number(value).toLocaleString(I18N.language(), { maximumFractionDigits: digits });
}

/** Formats saved integer minor units without mixing currencies. */
function money(cost) {
    return new Intl.NumberFormat(I18N.language(), { style: "currency", currency: cost.currency }).format(cost.costMinor / 100);
}

/** Shows one accessible outcome near the page heading. */
function message(text, bad = false) {
    const box = control("acc-message");
    box.textContent = text;
    box.classList.toggle("bad", bad);
    box.hidden = false;
}

/** Returns the selected inclusive calendar dates as a half-open time interval. */
function interval() {
    const params = new URLSearchParams();
    if (control("acc-from").value) params.set("from", String(new Date(`${control("acc-from").value}T00:00:00`).getTime()));
    if (control("acc-until").value) {
        const until = new Date(`${control("acc-until").value}T00:00:00`);
        until.setDate(until.getDate() + 1);
        params.set("until", String(until.getTime()));
    }
    return params;
}

/** Loads one report, discarding a response superseded by a newer filter change. */
async function loadReport() {
    const generation = ++reportGeneration;
    control("acc-export").disabled = true;
    const printer = control("acc-printer").value;
    if (!printer) { report = { bookings: [], printCount: 0, grams: 0, reviewCount: 0, totals: [], unknownCostCount: 0 }; renderReport(); return; }
    try {
        const result = await fetchJson(`./api/print/${encodeURIComponent(printer)}/report?${interval()}`);
        if (generation !== reportGeneration) return;
        report = result;
        renderReport();
    } catch (error) { if (generation === reportGeneration) message(error.message, true); }
}

/** Draws the status using translated labels rather than technical API codes. */
function badge(status) {
    return `<span class="acc-badge ${esc(status)}">${esc(t(`accounting.status.${status}`))}</span>`;
}

/** Makes unresolved outcomes actionable without offering to resend their stock write. */
function reviewButton(record, kind) {
    return ["pending", "uncertain"].includes(record.status)
        ? `<button type="button" class="acc-review-button" data-review-id="${esc(record.id)}" data-review-kind="${kind}">${esc(t("accounting.reviewAction"))}</button>` : "";
}

/** Renders totals and a bounded history table from the server's report. */
function renderReport() {
    if (!report) return;
    control("acc-print-count").textContent = number(report.printCount, 0);
    control("acc-grams").textContent = `${number(report.grams)} ${t("accounting.grams")}`;
    control("acc-cost").textContent = report.totals.length === 1 ? money(report.totals[0]) : report.totals.length ? t("accounting.multipleCurrencies") : "—";
    control("acc-review").textContent = number(report.reviewCount, 0);
    control("acc-review-card").classList.toggle("needs-review", report.reviewCount > 0);
    const rows = report.bookings.filter(row => !control("acc-only-review").checked || ["pending", "uncertain"].includes(row.status)).slice(0, 100);
    control("acc-history-body").innerHTML = rows.map(row => `<tr>
        <td>${esc(new Date(row.startedAt).toLocaleDateString(I18N.language()))}<small>${esc(new Date(row.startedAt).toLocaleTimeString(I18N.language(), { hour: "2-digit", minute: "2-digit" }))}</small></td>
        <td><strong>${esc(row.jobName || t("accounting.unnamed"))}</strong><small>${esc(t(`accounting.terminal.${row.terminalState}`))}</small></td>
        <td>#${esc(row.spoolId)}<small>${esc(row.result?.filament?.name || row.itemKey)}</small></td>
        <td>${esc(number(row.grams))} ${esc(t("accounting.grams"))}</td>
        <td>${row.status === "booked" && row.cost ? esc(money(row.cost)) : "—"}</td><td>${badge(row.status)}${reviewButton(row, "booking")}</td></tr>`).join("");
    control("acc-empty").hidden = rows.length > 0;
    control("acc-report-totals").innerHTML = report.totals.map(total => `<article class="acc-report-currency"><span>${esc(total.currency)}</span><strong>${esc(money(total))}</strong></article>`).join("") || `<p class="acc-form-note">${esc(t("accounting.noCostYet"))}</p>`;
    control("acc-unknown-cost").textContent = `${t("accounting.unknownCost")}: ${number(report.unknownCostCount, 0)}`;
    control("acc-export").disabled = report.bookings.length === 0;
}

/** Refreshes inventory and local price/measurement data without replacing selection. */
async function loadInventory() {
    const [spools, accounting] = await Promise.all([fetchJson("./api/spoolman/spools"), fetchJson("./api/accounting")]);
    inventory = Array.isArray(spools) ? spools : [];
    profiles = accounting.profiles;
    weighings = accounting.weighings;
    const selected = control("acc-spool").value;
    control("acc-spool").innerHTML = inventory.map(spool => `<option value="${spool.id}">#${spool.id} · ${esc(spool.filament?.vendor?.name || "")} ${esc(spool.filament?.name || spool.filament?.material || t("accounting.unnamed"))}</option>`).join("");
    if (inventory.some(spool => String(spool.id) === selected)) control("acc-spool").value = selected;
    await selectSpool();
    renderWeighings();
}

/** Reads the selected spool afresh so a manual correction carries its current usage. */
async function selectSpool() {
    const id = control("acc-spool").value;
    currentSpool = null;
    for (const form of ["acc-weigh-form", "acc-cost-form"]) control(form).querySelector("button").disabled = true;
    if (!id) return;
    const spool = await fetchJson(`./api/spoolman/spool/${encodeURIComponent(id)}`);
    if (control("acc-spool").value !== id) return;
    currentSpool = spool;
    weighingId = crypto.randomUUID();
    control("acc-spool-detail").textContent = `${t("accounting.remaining")}: ${spool.remaining_weight == null ? t("accounting.unknown") : `${number(spool.remaining_weight)} ${t("accounting.grams")}`}`;
    const profile = profiles.find(entry => entry.spoolId === spool.id);
    control("acc-price").value = profile ? String(profile.priceMinor / 100) : "";
    control("acc-basis").value = profile ? String(profile.basisMilligrams / 1000) : String(spool.initial_weight ?? spool.filament?.weight ?? "");
    control("acc-currency").value = profile?.currency || "UAH";
    control("acc-tare").value = spool.spool_weight == null ? "" : String(spool.spool_weight);
    control("acc-gross").value = "";
    previewNet();
    for (const form of ["acc-weigh-form", "acc-cost-form"]) control(form).querySelector("button").disabled = false;
}

/** Previews gross minus tare; the server performs the authoritative exact validation. */
function previewNet() {
    const gross = control("acc-gross").value.replace(",", "."), tare = control("acc-tare").value.replace(",", ".");
    const net = Number(gross) - Number(tare);
    control("acc-net").textContent = gross && tare && Number.isFinite(net) && net >= 0 ? `${number(net)} ${t("accounting.grams")}` : "—";
}

/** Renders the recent manual scale entries, including attempts requiring review. */
function renderWeighings() {
    control("acc-weighings-body").innerHTML = weighings.map(row => `<tr><td>${esc(new Date(row.createdAt).toLocaleString(I18N.language()))}</td><td>#${esc(row.spoolId)}</td><td>${esc(number(row.netMilligrams / 1000))} ${esc(t("accounting.grams"))}</td><td>${badge(row.status)}${reviewButton(row, "weighing")}</td></tr>`).join("") || `<tr><td colspan="4">${esc(t("accounting.noWeighings"))}</td></tr>`;
}

/** Opens a review with a freshly read balance, preserving the selected occurrence. */
async function openReview(button) {
    const kind = button.dataset.reviewKind;
    const record = (kind === "booking" ? report?.bookings : weighings)?.find(entry => entry.id === button.dataset.reviewId);
    if (!record) return;
    try {
        const spool = await fetchJson(`./api/spoolman/spool/${record.spoolId}`);
        reviewTarget = { kind, id: record.id, printerId: control("acc-printer").value };
        control("acc-review-balance").textContent = `#${record.spoolId} · ${t("accounting.remaining")}: ${spool.remaining_weight == null ? t("accounting.unknown") : number(spool.remaining_weight) + " " + t("accounting.grams")}`;
        control("acc-review-resolution").value = "";
        control("acc-review-note").value = "";
        control("acc-review-dialog").showModal();
    } catch (error) { message(error.message, true); }
}

/** Saves an explicit human acknowledgement, with no further consumption or correction. */
async function saveReview(event) {
    event.preventDefault();
    if (!reviewTarget) return;
    const target = reviewTarget, button = event.currentTarget.querySelector("button[type=submit]");
    button.disabled = true;
    try {
        const url = target.kind === "booking"
            ? `./api/print/${encodeURIComponent(target.printerId)}/bookings/${encodeURIComponent(target.id)}/resolve`
            : `./api/accounting/weighings/${encodeURIComponent(target.id)}/resolve`;
        await sendJson(url, "POST", { resolution: control("acc-review-resolution").value, note: control("acc-review-note").value });
        control("acc-review-dialog").close();
        reviewTarget = null;
        message(t("accounting.reviewSaved"));
        await Promise.all([loadReport(), loadInventory()]);
    } catch (error) { control("acc-review-dialog").close(); message(error.message, true); }
    finally { button.disabled = false; }
}

/** Saves a price without retrospectively changing the cost of previous prints. */
async function savePrice(event) {
    event.preventDefault();
    if (!currentSpool) return;
    const spoolId = currentSpool.id, button = event.currentTarget.querySelector("button");
    button.disabled = true;
    try {
        const result = await sendJson(`./api/accounting/cost/${spoolId}`, "PUT", {
            price: control("acc-price").value, basisGrams: control("acc-basis").value,
            currency: control("acc-currency").value,
            expectedRevision: profiles.find(profile => profile.spoolId === spoolId)?.revision ?? 0,
        });
        profiles = result.profiles;
        message(t("accounting.priceSaved"));
    } catch (error) { message(error.message, true); }
    finally { button.disabled = false; }
}

/** Applies an explicit scale reading with the original request identity retained on failure. */
async function saveWeight(event) {
    event.preventDefault();
    if (!currentSpool) return;
    const button = event.currentTarget.querySelector("button");
    button.disabled = true;
    try {
        await sendJson(`./api/accounting/weigh/${currentSpool.id}`, "POST", {
            requestId: weighingId, grossGrams: control("acc-gross").value,
            tareGrams: control("acc-tare").value, expectedUsedWeight: currentSpool.used_weight,
        });
        message(t("accounting.weightSaved"));
        await loadInventory();
    } catch (error) { message(error.message, true); }
    finally { button.disabled = false; }
}

/** Escapes untrusted spreadsheet text, including formula prefixes, before CSV export. */
function csvCell(value) {
    let text = String(value ?? "");
    if (/^[\s\uFEFF]*[=+\-@]|^[\t\r\n]/.test(text)) text = `'${text}`;
    return `"${text.replaceAll('"', '""')}"`;
}

/** Exports the selected report with each currency and review state kept explicit. */
function exportReport() {
    if (!report) return;
    const rows = [[t("accounting.date"), t("accounting.job"), t("accounting.spool"), t("accounting.mass"), t("accounting.cost"), t("accounting.currency"), t("accounting.status")],
        ...report.bookings.map(row => [new Date(row.startedAt).toISOString(), row.jobName, row.spoolId, row.grams,
            row.status === "booked" && row.cost ? (row.cost.costMinor / 100).toFixed(2) : "",
            row.cost?.currency || "", t(`accounting.status.${row.status}`)])];
    const url = URL.createObjectURL(new Blob(["\uFEFF" + rows.map(row => row.map(csvCell).join(";")).join("\r\n")], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url; link.download = "haspelsync-filament-report.csv"; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Initializes the page with the installation's existing menu, theme and language. */
async function start() {
    initMenubar();
    const language = control("acc-language");
    language.innerHTML = I18N.languages().map(([code, name]) => `<option value="${esc(code)}">${esc(name)}</option>`).join("");
    language.value = I18N.language();
    language.addEventListener("change", () => { I18N.setLanguage(language.value); location.reload(); });
    document.querySelectorAll(".acc-tabs button").forEach(button => button.addEventListener("click", () => {
        document.querySelectorAll(".acc-tabs button").forEach(tab => tab.setAttribute("aria-selected", String(tab === button)));
        document.querySelectorAll(".acc-panel").forEach(panel => { panel.hidden = panel.id !== button.dataset.panel; });
    }));
    control("acc-printer").addEventListener("change", loadReport);
    for (const id of ["acc-from", "acc-until"]) control(id).addEventListener("change", loadReport);
    control("acc-only-review").addEventListener("change", renderReport);
    control("acc-spool").addEventListener("change", () => selectSpool().catch(error => message(error.message, true)));
    control("acc-gross").addEventListener("input", previewNet);
    control("acc-tare").addEventListener("input", previewNet);
    control("acc-cost-form").addEventListener("submit", savePrice);
    control("acc-weigh-form").addEventListener("submit", saveWeight);
    control("acc-export").addEventListener("click", exportReport);
    control("acc-review-form").addEventListener("submit", saveReview);
    control("acc-review-cancel").addEventListener("click", () => control("acc-review-dialog").close());
    for (const id of ["acc-history-body", "acc-weighings-body"]) control(id).addEventListener("click", event => {
        const button = event.target.closest("[data-review-id]");
        if (button) openReview(button);
    });
    control("acc-refresh").addEventListener("click", async () => {
        control("acc-message").hidden = true;
        try { await Promise.all([loadReport(), loadInventory()]); } catch (error) { message(error.message, true); }
    });
    try {
        const printers = await fetchJson("./api/printers");
        control("acc-printer").innerHTML = printers.map(printer => `<option value="${esc(printer.id)}">${esc(printer.name)}</option>`).join("");
        await Promise.all([loadReport(), loadInventory()]);
    } catch (error) { message(error.message, true); }
}

document.addEventListener("DOMContentLoaded", start);
