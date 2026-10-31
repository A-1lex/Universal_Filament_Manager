// Pure Haspel slice parsing and filament calculation; no service runtime imports.

import { normColor } from "../public/shared.js";

/**
 * The key one sliced filament is accumulated under, and the entry it seeds.
 *
 * The position in the slicer's filament list, which is one slot, so two
 * filaments never merge. They used to be accumulated under their identity, and
 * two identical black spools in two slots were therefore one number before
 * anything looked at the AMS; the sum could not be split afterwards however the
 * spools were identified. Keeping them apart costs nothing where the printer
 * cannot tell them apart either: both then match the same spool and book
 * separately, which adds up to the same total.
 *
 * The key is deliberately not the slot label. Which slot a position is depends
 * on the printer the print is booked against, and that is not known here.
 */
export function consumptionEntry(f) {
    return {
        key: `filament${f.index}`,
        entry: {
            index: f.index,
            tray_info_idx: f.tray_info_idx,
            color: f.color,
            colors: f.colors || null,
            type: f.type,
            // Both filled in by resolveSliceSlots, which needs the printer this
            // is going to be matched against and is therefore not known here.
            amsId: null,
            amsIdFromPrinter: false,
            grams: 0,
        },
    };
}

/**
 * Calculates consumed grams per sliced filament for a complete print. Purge is
 * already included in used_g from the slicer.
 *
 * Run the result through `resolveSliceSlots()` to name the slots before
 * matching it against a printer.
 *
 * @param {object} sliceInfo - result of fetchSliceInfo
 * @returns {{ [key]: { index, tray_info_idx, color, colors, type, amsId, grams } }}
 */
export function calcFullConsumption(sliceInfo) {
    const result = {};
    for (const f of sliceInfo.filaments) {
        if (!f.tray_info_idx) continue;
        const { key, entry } = consumptionEntry(f);
        if (!result[key]) result[key] = entry;
        result[key].grams += f.used_g;
    }
    return roundEntries(result);
}

/**
 * Calculates consumed grams per tray_info_idx up to a given layer (for
 * failed/cancelled prints).
 *
 * Each filament is scaled by the fraction of ITS active layers that were
 * printed. A filament's active layers are the union of all layer_filament_list
 * ranges that reference it. When a filament spans the whole print (the common
 * case) this reduces to completedLayers / totalLayers; when a filament is
 * restricted to certain layers (e.g. a different top color) the estimate is
 * more accurate.
 *
 * When the plate's G-code was read, `sliceInfo.extrusion` says how much of
 * each filament is used up by the end of every layer, and that share replaces
 * the layer count: the flush of a filament change then lands on the layer it
 * happens in, rather than being spread over every layer of the filament. A
 * filament the G-code was not trusted for keeps the layer count, see
 * `checkLayerExtrusion()`.
 *
 * `upToLayer` is the last completed layer as a 0-based index into the sliced
 * file's layers, which is not what the printer reports: see
 * `completedLayerIndex()` for the conversion from `layer_num`.
 *
 * @param {object} sliceInfo  - result of fetchSliceInfo
 * @param {number} upToLayer  - last completed layer, 0-based; -1 when none is
 * @returns {{ [key]: { tray_info_idx, color, type, grams } }}
 */
export function calcPartialConsumption(sliceInfo, upToLayer) {
    const result = {};

    for (const f of sliceInfo.filaments) {
        if (!f.tray_info_idx) continue;

        const ranges = sliceInfo.rangesByFilamentIdx[f.index] || [];
        const shares = sliceInfo.extrusion?.shares?.[f.index];

        // No layer data → fall back to global progress fraction
        let proportion;
        if (shares?.length) {
            // Index 0 of the shares is the start G-code, so the last
            // completed layer as a 0-based index is one further along
            proportion = shares[Math.min(upToLayer + 1, shares.length - 1)];
        } else if (ranges.length === 0) {
            proportion = sliceInfo.totalLayers > 0
                ? Math.min(1, (upToLayer + 1) / (sliceInfo.totalLayers + 1))
                : 0;
        } else {
            const total = ranges.reduce((s, [a, b]) => s + (b - a + 1), 0);
            let done = 0;
            for (const [start, end] of ranges) {
                if (upToLayer < start) continue;
                done += Math.min(upToLayer, end) - start + 1;
            }
            proportion = total > 0 ? done / total : 0;
        }

        const { key, entry } = consumptionEntry(f);
        if (!result[key]) result[key] = entry;
        result[key].grams += f.used_g * proportion;
    }

    return roundEntries(result);
}

/**
 * Parses `Metadata/slice_info.config` into the shape the consumption maths
 * expects.
 *
 * Two things are read out of it: the filament list, where each entry carries
 * the material profile, colour and the grams the slicer predicted, and the
 * layer_filament_list entries, which say over which layer ranges each filament
 * is actually used. Filament ids are 1 based and may be non contiguous, while
 * the layer lists reference a 0 based index, so both are kept.
 *
 * `projectSettings` is the sibling entry of the same archive. It is optional
 * and adds two things this file does not carry: the whole colour set of a
 * multi colour filament, and nothing else. slice_info.config keeps only the
 * first colour of a set, which is why a gradient spool and a plain spool of
 * the same first colour were one filament as far as this service could tell.
 *
 * Exported for tests; fetchSliceInfo is the normal entry point.
 *
 * @param {string} xml - the raw slice_info.config contents
 * @param {string|null} [projectSettings] - raw project_settings.config
 * @returns {{filaments: object[], totalLayers: number, rangesByFilamentIdx: object}}
 */
export function parseSliceInfo(xml, projectSettings = null) {
    const colorSets = parseMultiColours(projectSettings);
    const presets = parsePresets(projectSettings);

    // --- filaments ---
    const filaments = [];
    const filamentRe = /<filament\s+([^>]+?)\/>/g;
    let m;
    while ((m = filamentRe.exec(xml)) !== null) {
        const a = parseAttrs(m[1]);
        const id = parseInt(a.id, 10);
        if (!Number.isFinite(id)) continue;
        filaments.push({
            id,                       // 1-based, may be non-contiguous
            index: id - 1,            // 0-based index used in layer_filament_list
            tray_info_idx: a.tray_info_idx || null,
            type: a.type || null,
            color: a.color || null,
            colors: colorSets[id - 1] || null,
            used_m: parseFloat(a.used_m) || 0,
            used_g: parseFloat(a.used_g) || 0,
        });
    }

    // --- layer_filament_list: each entry lists the filament indices used over
    //     one or more layer ranges. Build per-filament-index merged ranges. ---
    const rangesByFilamentIdx = {};
    let totalLayers = 0;

    const listRe = /<layer_filament_list\s+([^>]+?)\/>/g;
    while ((m = listRe.exec(xml)) !== null) {
        const a = parseAttrs(m[1]);
        const indices = (a.filament_list || "")
            .trim().split(/\s+/).filter(s => s !== "").map(Number);
        const ranges = parseLayerRanges(a.layer_ranges || "");

        // A list without a filament prints nothing and does not count. A P2S
        // plate sliced by MakerWorld on 2026-09-26 carried one over "248 249"
        // after its 248 layers, which made the log say 250 and the partial
        // booking of a cancelled print divide by 250.
        if (!indices.length) continue;
        for (const [, end] of ranges) {
            if (end > totalLayers) totalLayers = end;
        }
        for (const idx of indices) {
            (rangesByFilamentIdx[idx] ||= []).push(...ranges);
        }
    }

    return { filaments, totalLayers, rangesByFilamentIdx, presets };
}

/**
 * The presets a project names, one per filament of the project, id, preset
 * name and vendor side by side.
 *
 * `project_settings.config` is JSON, and `filament_ids`, `filament_settings_id`
 * and `filament_vendor` are three lists in the same order. The id is what a
 * slot reports as `tray_info_idx` when that preset is chosen for it; for a
 * preset from Studio's cloud library that is a hash, and this is the only place
 * its name is written down. The "@BBL P2S 0.6 nozzle" tail of a preset name
 * says which printer profile it was made for and is dropped.
 *
 * @param {string|null} json - the file's text
 * @returns {{id: string, name: string|null, vendor: string|null}[]} empty when
 *   the file is missing or names no ids
 */
function parsePresets(json) {
    if (!json) return [];
    let parsed;
    try {
        parsed = JSON.parse(json);
    } catch {
        return [];
    }
    const ids = Array.isArray(parsed?.filament_ids) ? parsed.filament_ids : [];
    const names = Array.isArray(parsed?.filament_settings_id) ? parsed.filament_settings_id : [];
    const vendors = Array.isArray(parsed?.filament_vendor) ? parsed.filament_vendor : [];

    return ids.map((id, index) => {
        const rawName = typeof names[index] === "string" ? names[index].trim() : "";
        const name = rawName.replace(/\s*@.*$/, "").trim() || null;
        const vendor = typeof vendors[index] === "string" && vendors[index].trim() ? vendors[index].trim() : null;
        return { id: String(id ?? "").trim(), name, vendor };
    }).filter(preset => preset.id);
}

/**
 * Reads `filament_multi_colour` out of project_settings.config, indexed the way
 * the slicer indexes its filament list, so entry `id - 1` belongs to filament
 * `id`.
 *
 * The file is JSON, but it is parsed with a regular expression on purpose: it
 * is the slicer's whole configuration, tens of thousands of characters of
 * gcode templates and per filament arrays, and one key out of it does not
 * justify holding all of that as objects. A file that cannot be read at all
 * yields nothing, and the single colour each filament also carries stays the
 * only thing known about it.
 *
 * Studio writes a set as one space separated string, "#8EC9E9 #E7C1D5", and a
 * single colour filament as its one colour, so a set of one is not a set.
 *
 * @param {string|null} json - raw project_settings.config
 * @returns {string[][]} colour sets by filament index, sparse
 */
function parseMultiColours(json) {
    if (!json) return [];

    const match = /"filament_multi_colour"\s*:\s*\[([^\]]*)\]/.exec(json);
    if (!match) return [];

    return match[1]
        .split(",")
        .map(entry => {
            const colors = (entry.match(/"([^"]*)"/)?.[1] || "")
                .trim()
                .split(/\s+/)
                .map(normColor)
                .filter(Boolean);
            return colors.length > 1 ? colors : null;
        });
}

/**
 * Parses the `key="value"` attributes of one XML tag into an object. The slice
 * info file is small and machine generated, so this is used instead of pulling
 * in an XML parser.
 */
export function parseAttrs(str) {
    const result = {};
    const re = /(\w+)="([^"]*)"/g;
    let m;
    while ((m = re.exec(str)) !== null) result[m[1]] = m[2];
    return result;
}

/**
 * Parses a `layer_ranges` attribute into inclusive layer pairs.
 *
 * "0 127" yields [[0, 127]], "0 50,60 127" yields [[0, 50], [60, 127]].
 * Malformed pairs are dropped rather than producing NaN ranges.
 */
export function parseLayerRanges(str) {
    // "0 127" → [[0,127]];  "0 50,60 127" → [[0,50],[60,127]]
    return str.split(",")
        .map(pair => pair.trim().split(/\s+/).map(Number))
        .filter(([s, e]) => Number.isFinite(s) && Number.isFinite(e))
        .map(([s, e]) => [s, e]);
}

/** Rounds every consumption entry to two decimals, in place. */
function roundEntries(result) {
    for (const k of Object.keys(result)) {
        result[k].grams = Math.round(result[k].grams * 100) / 100;
    }
    return result;
}
