/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
 *
 * Minimal ServiceWorkerGlobalScope emulator, so the worker we SERVE is the
 * worker we TEST.
 *
 * Everything in `PUSH_HANDLERS` is a Python string until a phone runs it. The
 * Python suite could only ever assert that certain substrings were present,
 * which is why a mutation could delete the whole base64url re-encoding of the
 * VAPID key -- the one thing that keeps push alive after the push service
 * rotates an endpoint -- and every test stayed green.
 *
 * This runs the served bytes inside `node:vm` against stubs that model the
 * parts of the browser contract the worker actually depends on, in particular
 * the two ways `showNotification` REJECTS (see `showNotification` below).
 *
 * Usage:  node service_worker_harness.js <worker.js> <input.json>
 * stdout: a single JSON object. The assertions all live in Python.
 */
"use strict";

const fs = require("fs");
const vm = require("vm");

// The origin the worker believes it is installed on. Every same-origin check
// in the worker is judged against exactly this value.
const ORIGIN = "https://microsite.example";

// Appended to the served worker and evaluated in the same script, so it can
// reach the `const` bindings (which are lexical and never land on the global).
const PROBE = `
globalThis.__probe = {
    base64url: (bytes) => pushArrayBufferToBase64Url(new Uint8Array(bytes).buffer),
    targetUrl: (data) => pushTargetUrl(data),
    tag: (data) => pushTag(data),
    constants: () => ({
        channel: PUSH_CHANNEL_PATH,
        fallback: PUSH_FALLBACK_URL,
        subscribe: PUSH_SUBSCRIBE_URL,
        generic: PUSH_GENERIC_TITLE,
    }),
};
`;

function freshRecord() {
    return {
        attempts: [],
        shown: [],
        matchAll: [],
        openWindow: [],
        focus: [],
        fetch: [],
        subscribeCalls: 0,
        getSubscriptionCalls: 0,
        errors: [],
    };
}

/** A `PushSubscription`, as much of one as the worker touches. */
function makeSubscription(spec, keyBytes) {
    if (!spec) {
        return null;
    }
    const key = spec.applicationServerKey === "absent"
        ? null
        : new Uint8Array(keyBytes);
    return {
        endpoint: spec.endpoint,
        options: {applicationServerKey: key, userVisibleOnly: true},
        toJSON() {
            return {
                endpoint: spec.endpoint,
                keys: spec.keys || {p256dh: "p256dh-value", auth: "auth-value"},
                expirationTime: spec.expirationTime === undefined
                    ? null
                    : spec.expirationTime,
            };
        },
    };
}

function buildScope(rec, testCase, keyBytes) {
    const handlers = {};

    const registration = {
        /**
         * The browser contract, not a yes-man.
         *
         * Both rejections below are real and were both reproduced against the
         * previous worker, where the rejected promise went into `waitUntil`
         * with no `.catch` and NOTHING was shown -- the `userVisibleOnly`
         * breach that costs the origin its push permission.
         */
        showNotification(title, options) {
            const opts = options || {};
            if ("actions" in opts && !Array.isArray(opts.actions)) {
                rec.attempts.push({title, options: opts, ok: false});
                return Promise.reject(
                    new TypeError("Failed to convert value to 'sequence'")
                );
            }
            if (opts.renotify && !opts.tag) {
                rec.attempts.push({title, options: opts, ok: false});
                return Promise.reject(
                    new TypeError(
                        "Notifications which set the renotify flag must " +
                        "specify a non-empty tag"
                    )
                );
            }
            rec.attempts.push({title, options: opts, ok: true});
            rec.shown.push({title, options: opts});
            return Promise.resolve();
        },
        pushManager: {
            subscribe(options) {
                rec.subscribeCalls += 1;
                return Promise.resolve(
                    makeSubscription(
                        testCase.resubscribed || {endpoint: "https://push.example/new"},
                        keyBytes
                    )
                );
            },
            getSubscription() {
                rec.getSubscriptionCalls += 1;
                return Promise.resolve(
                    makeSubscription(testCase.liveSubscription, keyBytes)
                );
            },
        },
    };

    const windowClients = (testCase.windowClients || []).map((url) => ({
        url,
        focus() {
            rec.focus.push(url);
            return Promise.resolve();
        },
    }));

    const self = {
        location: new URL(ORIGIN + "/service-worker.js"),
        registration,
        clients: {
            matchAll(options) {
                rec.matchAll.push(options);
                return Promise.resolve(windowClients);
            },
            openWindow(url) {
                rec.openWindow.push(url);
                return Promise.resolve(null);
            },
            claim: () => Promise.resolve(),
        },
        skipWaiting: () => Promise.resolve(),
        addEventListener(type, handler) {
            (handlers[type] = handlers[type] || []).push(handler);
        },
    };

    function fetchStub(url, init) {
        const options = init || {};
        let body = null;
        try {
            body = JSON.parse(options.body);
        } catch (error) {
            body = options.body === undefined ? null : String(options.body);
        }
        rec.fetch.push({
            url: String(url),
            method: options.method || null,
            credentials: options.credentials || null,
            headers: options.headers || null,
            body,
        });
        const answer = testCase.fetchResponse || {ok: true, status: 200, json: {}};
        if (answer.networkError) {
            return Promise.reject(new TypeError("Failed to fetch"));
        }
        return Promise.resolve({
            ok: answer.ok,
            status: answer.status,
            json: () =>
                answer.jsonThrows
                    ? Promise.reject(new SyntaxError("Unexpected token"))
                    : Promise.resolve(answer.json),
        });
    }

    // `website_pwa`'s own handlers use these two bare globals. Stubbed so the
    // served file evaluates as a whole -- we test the bytes that ship, not an
    // excerpt of them.
    const caches = {
        open: () => Promise.resolve({add: () => Promise.resolve()}),
        keys: () => Promise.resolve([]),
        match: () => Promise.resolve(undefined),
        delete: () => Promise.resolve(true),
    };

    const consoleStub = {
        error: (...args) => rec.errors.push(args.map(String).join(" ")),
        warn: (...args) => rec.errors.push(args.map(String).join(" ")),
        log: () => {},
    };

    return {handlers, sandbox: {
        self,
        caches,
        fetch: fetchStub,
        console: consoleStub,
        // A fresh vm realm has the ECMAScript built-ins but none of the host
        // ones, and `URL` is exactly the host object the same-origin check
        // now depends on.
        URL,
        btoa,
        atob,
    }};
}

/** Fire one event and wait for everything the handlers passed to waitUntil. */
async function dispatch(handlers, type, event) {
    const pending = [];
    event.waitUntil = (value) => {
        pending.push(Promise.resolve(value));
    };
    for (const handler of handlers[type] || []) {
        handler(event);
    }
    // A handler that rejects must not abort the run: recording that nothing
    // was shown IS the observation the defect-2 test makes.
    await Promise.allSettled(pending);
}

function buildEvent(testCase, keyBytes) {
    if (testCase.event === "push") {
        let data = null;
        if (!testCase.noData) {
            data = {
                json() {
                    if (testCase.payloadInvalid) {
                        throw new SyntaxError("Unexpected token in JSON");
                    }
                    return testCase.payload;
                },
            };
        }
        return {data};
    }
    if (testCase.event === "notificationclick") {
        return {
            notification: {
                data: testCase.notificationData,
                close() {},
            },
        };
    }
    // `PushSubscriptionChangeEvent`. Both members are real `PushSubscription`
    // objects when present, so a handler that reads `newSubscription` gets
    // something it can actually call `toJSON()` on -- Firefox's shape.
    const specs = testCase.subscriptions || {};
    return {
        oldSubscription: makeSubscription(specs.oldSubscription, keyBytes),
        newSubscription: makeSubscription(specs.newSubscription, keyBytes),
    };
}

async function main() {
    const source = fs.readFileSync(process.argv[2], "utf8");
    const input = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
    const keyBytes = input.keyBytes || [];
    const result = {cases: {}};

    for (const testCase of input.cases) {
        const rec = freshRecord();
        const {handlers, sandbox} = buildScope(rec, testCase, keyBytes);
        const context = vm.createContext(sandbox);
        vm.runInContext(source + "\n" + PROBE, context, {filename: "service-worker.js"});

        if (testCase.event) {
            const type = testCase.event === "subscriptionchange"
                ? "pushsubscriptionchange"
                : testCase.event;
            await dispatch(handlers, type, buildEvent(testCase, keyBytes));
        }
        const probe = context.__probe;
        rec.constants = probe.constants();
        if (testCase.base64urlOf) {
            rec.base64url = probe.base64url(testCase.base64urlOf);
        }
        if (testCase.targetUrlOf !== undefined) {
            rec.targetUrl = probe.targetUrl(testCase.targetUrlOf);
        }
        result.cases[testCase.name] = rec;
    }
    process.stdout.write(JSON.stringify(result));
}

main().catch((error) => {
    process.stdout.write(
        JSON.stringify({harnessError: String(error && error.stack) || String(error)})
    );
    process.exitCode = 1;
});
