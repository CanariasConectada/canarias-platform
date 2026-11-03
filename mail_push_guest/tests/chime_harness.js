/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
 *
 * Runs static/src/js/chime.js in node and reports what it did.
 *
 * Usage:  node chime_harness.js <chime.js> <input.json>
 * stdout: one JSON object {cases: {name: observation}}. The assertions all
 * live in Python (test_chime_js.py).
 *
 * The module is framework-free: its `export` keywords are removed and the
 * source is evaluated in a fresh `vm` realm per case, so the served bytes
 * are the tested bytes.
 */
"use strict";

const fs = require("fs");
const vm = require("vm");

function load(source, extraGlobals) {
    const plain = source.replace(/^export\s+/gm, "");
    const context = vm.createContext(Object.assign({console, Promise, Date}, extraGlobals));
    vm.runInContext(
        plain +
            "\n;globalThis.__api = {Chime, CHIME_MIN_INTERVAL_MS, MESSAGE_SOUND_KEY," +
            " createAudioPlayer, pageInView};",
        context
    );
    return context.__api;
}

function memoryStorage(initial) {
    const data = Object.assign({}, initial || {});
    return {
        data,
        getItem: (key) => (key in data ? data[key] : null),
        setItem: (key, value) => {
            data[key] = String(value);
        },
        removeItem: (key) => {
            delete data[key];
        },
    };
}

/**
 * A case is a list of steps against ONE Chime:
 *   {at: ms, ring: {ownMessage, inView}}  -> records true/false
 *   {mute: true|false}
 */
function runChimeCase(api, testCase) {
    let now = 0;
    let played = 0;
    const storage = testCase.storage === "throws"
        ? {
              getItem() {
                  throw new Error("SecurityError");
              },
              setItem() {
                  throw new Error("SecurityError");
              },
              removeItem() {
                  throw new Error("SecurityError");
              },
          }
        : memoryStorage(testCase.storage);
    const chime = new api.Chime({
        clock: () => now,
        storage,
        player: () => {
            played += 1;
        },
    });
    const rang = [];
    for (const step of testCase.steps || []) {
        if ("mute" in step) {
            chime.muted = step.mute;
            continue;
        }
        now = step.at;
        rang.push(chime.ring(step.ring || {}));
    }
    return {rang, played, muted: chime.muted, storage: storage.data || null};
}

/** Two documents of one origin (two tabs, a page and its framed chat). */
function runSharedCase(api, testCase) {
    let now = 0;
    let played = 0;
    const storage = memoryStorage();
    const player = () => {
        played += 1;
    };
    const first = new api.Chime({clock: () => now, storage, player});
    const second = new api.Chime({clock: () => now, storage, player});
    const rang = [];
    for (const step of testCase.steps) {
        now = step.at;
        rang.push((step.doc === 2 ? second : first).ring({}));
    }
    return {rang, played};
}

function runPlayerCase(api, testCase) {
    const created = [];
    class FakeAudio {
        constructor() {
            this.plays = 0;
            this.currentTime = 5;
            created.push(this);
        }
        canPlayType(type) {
            return testCase.ogg && type.includes("ogg") ? "probably" : "";
        }
        play() {
            this.plays += 1;
            return testCase.rejects ? Promise.reject(new Error("NotAllowedError")) : Promise.resolve();
        }
    }
    const play = api.createAudioPlayer(FakeAudio);
    play();
    play();
    return {
        created: created.length,
        src: created[0] && created[0].src,
        plays: created[0] && created[0].plays,
        currentTime: created[0] && created[0].currentTime,
    };
}

function runInViewCase(api, testCase) {
    return {
        inView: api.pageInView({
            visibilityState: testCase.visibility,
            hasFocus: () => testCase.focus,
        }),
    };
}

async function main() {
    const [chimePath, inputPath] = process.argv.slice(2);
    const source = fs.readFileSync(chimePath, "utf8");
    const input = JSON.parse(fs.readFileSync(inputPath, "utf8"));
    const out = {constants: null, cases: {}};
    for (const testCase of input.cases) {
        const api = load(source, {});
        if (!out.constants) {
            out.constants = {
                interval: api.CHIME_MIN_INTERVAL_MS,
                key: api.MESSAGE_SOUND_KEY,
            };
        }
        let observed;
        if (testCase.kind === "player") {
            observed = runPlayerCase(api, testCase);
        } else if (testCase.kind === "shared") {
            observed = runSharedCase(api, testCase);
        } else if (testCase.kind === "inView") {
            observed = runInViewCase(api, testCase);
        } else {
            observed = runChimeCase(api, testCase);
        }
        // Let the rejected play() promises settle: an unhandled rejection
        // would be a crash on a real page's console.
        await new Promise((resolve) => setTimeout(resolve, 0));
        out.cases[testCase.name] = observed;
    }
    process.stdout.write(JSON.stringify(out));
}

process.on("unhandledRejection", (error) => {
    process.stdout.write(JSON.stringify({harnessError: "unhandled rejection: " + error}));
    process.exit(1);
});

main().catch((error) => {
    process.stdout.write(JSON.stringify({harnessError: String(error && error.stack)}));
    process.exit(1);
});
