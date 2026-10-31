// Experimental read-only boundary: no MQTT, FTPS, Spoolman client or ledger API.
// Uses only pure calculation exports; not installed in UFM Studio.
const MAX_BYTES = 512 * 1024;
let requestId = null;
try {
    let size = 0;
    const chunks = [];
    for await (const chunk of process.stdin) {
        size += chunk.length;
        if (size > MAX_BYTES) throw new Error("request_too_large");
        chunks.push(chunk);
    }
    const text = new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(chunks));
    const request = JSON.parse(text);
    requestId = request.request_id;
    if (request.v !== 1 || request.op !== "calculate" || typeof requestId !== "string" ||
        !/^[a-zA-Z0-9_-]{1,64}$/.test(requestId)) throw new Error("invalid_envelope");
    if (typeof request.xml !== "string" || /<!DOCTYPE|<!ENTITY/i.test(request.xml)) {
        throw new Error("unsupported_xml");
    }
    const layer = request.up_to_layer;
    if (layer !== null && (!Number.isInteger(layer) || layer < -1 || layer > 1000000)) {
        throw new Error("invalid_layer");
    }
    const { parseSliceInfo, calcFullConsumption, calcPartialConsumption } =
        await import("../../linked-stack/haspelsync/src/gcode.js");
    const slice = parseSliceInfo(request.xml);
    if (!slice.filaments.length || slice.filaments.length > 256) throw new Error("invalid_filaments");
    const seen = new Set();
    for (const item of slice.filaments) {
        if (!Number.isInteger(item.id) || item.id < 1 || item.id > 256 || seen.has(item.id) ||
            !Number.isFinite(item.used_g) || item.used_g < 0 || item.used_g > 10000 ||
            !/^[a-zA-Z0-9_-]{1,64}$/.test(item.tray_info_idx ?? "") ||
            !/^#?[a-fA-F0-9]{6,8}$/.test(item.color ?? "")) throw new Error("invalid_filaments");
        seen.add(item.id);
    }
    const full = calcFullConsumption(slice);
    const partial = layer === null ? null : calcPartialConsumption(slice, layer);
    for (const item of [...Object.values(full), ...Object.values(partial ?? {})]) {
        if (!Number.isFinite(item.grams) || item.grams < 0) throw new Error("invalid_result");
    }
    process.stdout.write(JSON.stringify({ v: 1, request_id: requestId, ok: true,
        data: { full, partial, total_layers: slice.totalLayers,
            logical_ids: slice.filaments.map(item => item.id),
            policy: "haspel-1.3.4-local.1-two-decimal-grams" } }));
} catch {
    // Do not echo filenames, request payloads or raw dependency exception text.
    process.stdout.write(JSON.stringify({ v: 1, request_id: requestId, ok: false,
        error: { code: "calculation_rejected" } }));
    process.exitCode = 2;
}
