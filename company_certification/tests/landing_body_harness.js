/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
 *
 * Runs the SHIPPED `static/src/interactions/landing_body_logic.js` in
 * `node:vm` and reports what each helper answers. The harness only calls and
 * reports; every assertion lives in tests/test_landing_body_js.py.
 *
 * Usage:  node landing_body_harness.js <landing_body_logic.js> <input.json>
 * stdout: a single JSON object {constants, results: {<case name>: <answer>}}.
 */
"use strict";

const fs = require("fs");
const vm = require("vm");

const API = [
    "CAROUSEL_INTERVAL",
    "carouselOptions",
    "panelsToClose",
    "keyAction",
    "targetIdFromHref",
    "triggerKind",
    "ariaFor",
    "indicatorLabel",
    "indicatorStates",
];

function loadApi(sourcePath) {
    const raw = fs.readFileSync(sourcePath, "utf8");
    if (/^\s*import\s/m.test(raw)) {
        throw new Error("landing_body_logic.js must stay import-free to be testable");
    }
    // No imports: dropping the `export` keyword is all it takes to evaluate
    // the file as a classic script.
    const source = raw.replace(/^export\s+/gm, "");
    const probe = `\nglobalThis.__api = { ${API.join(", ")} };\n`;
    const context = vm.createContext({ JSON, Number, Math, String, Array, Boolean, Object });
    context.decodeURIComponent = decodeURIComponent;
    vm.runInContext(source + probe, context, { filename: sourcePath });
    return context.__api;
}

function main() {
    const [sourcePath, inputPath] = process.argv.slice(2);
    const api = loadApi(sourcePath);
    const input = JSON.parse(fs.readFileSync(inputPath, "utf8"));
    const results = {};
    for (const { name, fn, args } of input.calls) {
        if (typeof api[fn] !== "function") {
            throw new Error(`unknown helper: ${fn}`);
        }
        results[name] = api[fn](...args);
    }
    return { constants: { interval: api.CAROUSEL_INTERVAL }, results };
}

try {
    // `undefined` does not survive JSON: report it as null like a missing key.
    process.stdout.write(JSON.stringify(main(), (_key, value) => (value === undefined ? null : value)));
} catch (error) {
    process.stdout.write(JSON.stringify({ harnessError: String(error && error.stack ? error.stack : error) }));
}
