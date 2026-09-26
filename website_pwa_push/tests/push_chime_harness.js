/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
 *
 * Runs static/src/js/push_chime.js with its imports stubbed and reports what
 * it asked the chime for.
 *
 * Usage:  node push_chime_harness.js <push_chime.js> <input.json>
 *   case: {name, data, persona, android, permission, focused, chatChannelId,
 *          activeIframe}
 * stdout: {"cases": {<name>: {returned, ring}}}; assertions in Python.
 */
"use strict";

const fs = require("fs");

function load(source, deps) {
    const body = source
        .split("\n")
        .filter((line) => !/^import\s/.test(line))
        .join("\n")
        .replace(/^export\s+/gm, "");
    // eslint-disable-next-line no-new-func
    return new Function(
        "deps",
        `const {chime, pageInView, isAndroid, user, session} = deps;\n${body}\n` +
            "return {onWorkerMessage, isOwnPush};"
    )(deps);
}

const [scriptPath, inputPath] = process.argv.slice(2);
try {
    const source = fs.readFileSync(scriptPath, "utf8");
    const input = JSON.parse(fs.readFileSync(inputPath, "utf8"));
    const cases = {};
    for (const testCase of input.cases) {
        const rings = [];
        const api = load(source, {
            chime: {
                ring(facts) {
                    rings.push(facts);
                    return !facts.ownMessage && !facts.inView;
                },
            },
            pageInView: () => Boolean(testCase.focused),
            isAndroid: () => false,
            user: {partnerId: 0},
            session: {},
        });
        globalThis.Notification = {permission: testCase.permission || "default"};
        const doc = {
            activeElement: testCase.activeIframe ? {tagName: "IFRAME"} : {tagName: "BODY"},
            querySelector: (selector) =>
                testCase.chatChannelId &&
                selector === `.o_cc_chat[data-channel-id="${testCase.chatChannelId}"]`
                    ? {}
                    : null,
        };
        const returned = api.onWorkerMessage(
            {data: {type: testCase.type || "notification-displayed", payload: testCase.data}},
            {doc, android: Boolean(testCase.android), persona: testCase.persona || {}}
        );
        cases[testCase.name] = {returned, ring: rings[0] || null};
    }
    process.stdout.write(JSON.stringify({cases}));
} catch (error) {
    process.stdout.write(JSON.stringify({harnessError: String(error && error.stack)}));
    process.exit(1);
}
