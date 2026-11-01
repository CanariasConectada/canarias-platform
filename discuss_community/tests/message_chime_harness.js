/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
 *
 * Runs static/src/backend/message_chime_rules.js (no imports) in node.
 *
 * Usage:  node message_chime_harness.js <message_chime_rules.js> <input.json>
 * stdout: {"cases": {<name>: <boolean>}}; assertions live in Python.
 */
"use strict";

const fs = require("fs");
const vm = require("vm");

const [rulesPath, inputPath] = process.argv.slice(2);
try {
    const source = fs.readFileSync(rulesPath, "utf8").replace(/^export\s+/gm, "");
    const context = vm.createContext({});
    vm.runInContext(source + "\n;globalThis.__rule = shouldChimeForChannelMessage;", context);
    const input = JSON.parse(fs.readFileSync(inputPath, "utf8"));
    const cases = {};
    for (const testCase of input.cases) {
        cases[testCase.name] = context.__rule(testCase.facts);
    }
    process.stdout.write(JSON.stringify({cases}));
} catch (error) {
    process.stdout.write(JSON.stringify({harnessError: String(error && error.stack)}));
    process.exit(1);
}
