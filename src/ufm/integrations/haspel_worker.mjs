// Canonical source-tree calculation entrypoint. Packaging the engine/runtime
// is a separate release task. This module has no MQTT/API/ledger command path.
const MAX_BYTES = 512 * 1024;
try {
    let size = 0;
    const chunks = [];
    for await (const chunk of process.stdin) {
        size += chunk.length;
        if (size > MAX_BYTES) throw new Error();
        chunks.push(chunk);
    }
    const request = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(chunks)));
    if (request.v !== 1 || request.kind !== "calculate" ||
        typeof request.metadata_xml !== "string" || /<!DOCTYPE|<!ENTITY/i.test(request.metadata_xml) ||
        !Array.isArray(request.materials) || request.materials.length < 1 || request.materials.length > 256) {
        throw new Error();
    }
    const partial = request.completed_layer !== null;
    const policy = partial ? "haspel-range-cent-preview-v1" : "three-mf-full-mg-preview-v1";
    if (request.policy_version !== policy || (partial && (!Number.isInteger(request.completed_layer) ||
        request.completed_layer < -1 || request.completed_layer > 1000000))) throw new Error();
    const { parseSliceInfo, calcPartialConsumption } =
        await import("./haspel_engine/calculation.js");
    const slice = parseSliceInfo(request.metadata_xml);
    const byId = new Map(slice.filaments.map(item => [item.index, item]));
    if (byId.size !== slice.filaments.length || byId.size !== request.materials.length) throw new Error();
    const seen = new Set();
    const materials = request.materials.map(item => {
        const logical = item.logical_material;
        if (!Number.isInteger(logical) || logical < 0 || logical > 255 || seen.has(logical) ||
            !Number.isSafeInteger(item.mass_mg) || item.mass_mg < 0 || item.mass_mg > 10000000 ||
            !byId.has(logical)) throw new Error();
        seen.add(logical);
        let mass = item.mass_mg;
        if (partial && mass > 0) {
            const ranges = slice.rangesByFilamentIdx[logical];
            // Global-progress fallback requires a separate, lower-confidence
            // policy; this range policy must not silently activate it.
            if (!ranges?.length) throw new Error();
            const last = Math.max(...ranges.map(([, end]) => end));
            if (request.completed_layer >= last) {
                return { logical_material: logical, mass_mg: mass };
            }
            // Isolate each logical material: legacy profile/color aggregation
            // must never collapse two channels assigned to different spools.
            const filament = { ...byId.get(logical), used_g: mass / 1000,
                tray_info_idx: "UFM_LOGICAL_" + logical, color: "FFFFFF" };
            const result = calcPartialConsumption({ ...slice, filaments: [filament] }, request.completed_layer);
            const grams = Object.values(result).reduce((sum, value) => sum + value.grams, 0);
            if (!Number.isFinite(grams) || grams < 0) throw new Error();
            // Legacy partial resolution is 0.01g; cap it at exact full-file mg.
            mass = Math.min(mass, Math.round(grams * 1000));
        }
        return { logical_material: logical, mass_mg: mass };
    });
    process.stdout.write(JSON.stringify({
        v: 1, kind: "proposal", request_id: request.request_id, printer_id: request.printer_id,
        source_epoch: request.source_epoch, sequence: request.sequence, observed_at: request.observed_at,
        occurrence_key: request.occurrence_key, file_sha256: request.file_sha256,
        evidence_id: request.evidence_id, policy_version: policy, quantity: "estimate",
        label: "Розрахункова витрата", confidence_bp: 0, status: "needs_mapping",
        partial, materials, allocations: [],
    }));
} catch {
    process.stdout.write('{"error":"worker.calculation_rejected"}');
    process.exitCode = 2;
}
