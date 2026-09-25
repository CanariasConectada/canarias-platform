/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
 *
 * Runs the PAGE script (static/src/js/pwa_push.js) outside a browser, against
 * fakes of the parts of the Push API it orchestrates: service worker
 * registrations, PushManager, subscriptions, worker state changes and the
 * worker -> page message channel.
 *
 * Same contract as service_worker_harness.js: this file only drives and
 * observes, every assertion lives in Python. The module is the shipped file,
 * with its ES `import`/`export` keywords stripped and its four framework
 * imports (registry, Interaction, rpc, user, PWAInstall) replaced by stubs.
 *
 * Usage:  node page_script_harness.js <pwa_push.js> <input.json>
 * stdout: a single JSON object {"cases": {<name>: <observations>}}.
 */
"use strict";

const fs = require("fs");
const vm = require("vm");

const ORIGIN = "https://app.example";

const EXPORTED = [
    "PWAPush",
    "PWAPushOpenChannel",
    "pushTarget",
    "whenActive",
    "discussChannelUrl",
    "base64UrlToUint8Array",
    "arrayBufferToBase64Url",
    "BACKEND_WORKER_URL",
    "BACKEND_WORKER_SCOPE",
    "CORE_ENDPOINT_STORAGE_KEY",
];

function moduleFactorySource(source) {
    const body = source
        .split("\n")
        .filter((line) => !/^import\s/.test(line))
        .join("\n")
        .replace(/^export\s+(?=(async\s+)?(class|function|const)\b)/gm, "");
    return `(function (deps) {
        const {registry, Interaction, rpc, user, PWAInstall} = deps;
        ${body}
        return {${EXPORTED.join(", ")}};
    })`;
}

function freshRecord() {
    return {
        register: [],
        readyUsed: 0,
        getRegistration: [],
        subscribeCalls: [],
        unsubscribed: [],
        rpc: [],
        storage: {},
        assigned: [],
        warnings: [],
        errors: [],
        startMessages: 0,
        result: null,
    };
}

function makeWorker(state) {
    const listeners = [];
    return {
        state,
        addEventListener(type, fn) {
            if (type === "statechange") {
                listeners.push(fn);
            }
        },
        transition(next) {
            this.state = next;
            for (const fn of listeners) {
                fn();
            }
        },
    };
}

function makeSubscription(endpoint, keyBytes, record) {
    return {
        endpoint,
        options: {
            applicationServerKey: keyBytes ? new Uint8Array(keyBytes).buffer : null,
        },
        toJSON() {
            return {endpoint, keys: {p256dh: "p256dh-value", auth: "auth-value"}, expirationTime: null};
        },
        unsubscribe() {
            record.unsubscribed.push(endpoint);
            return Promise.resolve(true);
        },
    };
}

/** A ServiceWorkerRegistration. `spec` null means "no registration". */
function makeRegistration(name, spec, record) {
    if (!spec) {
        return undefined;
    }
    let subscription = spec.subscription
        ? makeSubscription(spec.subscription.endpoint, spec.subscription.keyBytes, record)
        : null;
    return {
        name,
        scope: `${ORIGIN}${spec.scope}`,
        active: spec.worker === "active" ? makeWorker("activated") : null,
        installing: spec.worker === "installing" ? makeWorker("installing") : null,
        waiting: spec.worker === "waiting" ? makeWorker("installed") : null,
        pushManager: {
            getSubscription() {
                return Promise.resolve(subscription);
            },
            subscribe(options) {
                const keyBytes = Array.from(new Uint8Array(options.applicationServerKey));
                record.subscribeCalls.push({
                    registration: name,
                    userVisibleOnly: options.userVisibleOnly,
                    keyBytes,
                });
                subscription = makeSubscription(spec.newEndpoint, keyBytes, record);
                return Promise.resolve(subscription);
            },
        },
    };
}

function makeStorage(bag) {
    return {
        getItem: (key) => (key in bag ? bag[key] : null),
        setItem: (key, value) => {
            bag[key] = String(value);
        },
        removeItem: (key) => {
            delete bag[key];
        },
    };
}

function tick() {
    return new Promise((resolve) => setImmediate(resolve));
}

async function runCase(factorySource, spec, vapidKey) {
    const record = freshRecord();
    const registrations = {
        backend: makeRegistration("backend", spec.backend, record),
        website: makeRegistration("website", spec.website, record),
    };
    const messageListeners = [];
    const serviceWorker = {
        register(url, options) {
            record.register.push({url, scope: options && options.scope});
            const registration = registrations.backend;
            if (spec.activateAfterRegister && registration && registration.installing) {
                setImmediate(() => registration.installing.transition("activated"));
            }
            return Promise.resolve(registration);
        },
        get ready() {
            record.readyUsed++;
            return Promise.resolve(registrations.website);
        },
        getRegistration(scope) {
            record.getRegistration.push(scope);
            return Promise.resolve(scope === "/" ? registrations.website : undefined);
        },
        addEventListener(type, fn) {
            if (type === "message") {
                messageListeners.push(fn);
            }
        },
        startMessages() {
            record.startMessages++;
        },
    };
    const navigator = {serviceWorker, userAgent: "Harness", platform: "Linux", maxTouchPoints: 0};
    const window = {
        atob,
        btoa,
        navigator,
        localStorage: makeStorage(record.storage),
        sessionStorage: makeStorage({}),
        location: {
            origin: ORIGIN,
            assign(url) {
                record.assigned.push(url);
            },
        },
        matchMedia: () => ({matches: false}),
    };
    const fakeConsole = {
        log() {},
        warn: (...args) => record.warnings.push(args.map(String).join(" ")),
        error: (...args) => record.errors.push(args.map(String).join(" ")),
    };
    const context = vm.createContext({
        window,
        navigator,
        document: {querySelector: () => null},
        console: fakeConsole,
        URL,
        setTimeout,
        setImmediate,
    });

    class Interaction {
        constructor(el) {
            this.el = el || {
                dataset: {},
                classList: {add() {}, remove() {}},
                querySelector: () => null,
            };
        }
        waitFor(promise) {
            return promise;
        }
        addListener(target, type, fn) {
            target.addEventListener(type, fn);
        }
    }
    const deps = {
        registry: {category: () => ({add() {}})},
        Interaction,
        rpc: (route, params) => {
            record.rpc.push({route, params: params || {}});
            if (route === "/mail/push/vapid") {
                return Promise.resolve({vapid_public_key: vapidKey});
            }
            return Promise.resolve(true);
        },
        user: {isInternalUser: false, userId: false},
        PWAInstall: {prototype: {isIOS: () => false, isStandalone: () => false}},
    };
    const mod = vm.runInContext(factorySource, context)(deps);

    const settle = (promise) =>
        Promise.race([
            promise.then(
                (value) => ({state: "resolved", value}),
                (error) => ({state: "rejected", message: String(error && error.message)})
            ),
            new Promise((resolve) => setTimeout(() => resolve({state: "pending"}), 500)),
        ]);

    switch (spec.scenario) {
        case "constants":
            record.result = {
                coreEndpointKey: mod.CORE_ENDPOINT_STORAGE_KEY,
                backendUrl: mod.BACKEND_WORKER_URL,
                backendScope: mod.BACKEND_WORKER_SCOPE,
            };
            break;
        case "subscribe": {
            const push = new mod.PWAPush();
            push.target = spec.target;
            record.result = await settle(push.subscribe());
            break;
        }
        case "pushRegistration": {
            const push = new mod.PWAPush();
            push.target = spec.target;
            const outcome = await settle(push.pushRegistration());
            record.result = outcome.state === "resolved" ? outcome.value && outcome.value.name : outcome;
            break;
        }
        case "whenActive": {
            const registration = makeRegistration("probe", spec.registration, record);
            const pending = settle(mod.whenActive(registration));
            if (spec.transition) {
                await tick();
                (registration.installing || registration.waiting).transition(spec.transition);
            }
            record.result = await pending;
            break;
        }
        case "openChannel": {
            const interaction = new mod.PWAPushOpenChannel();
            interaction.start();
            for (const fn of messageListeners) {
                fn({data: spec.message});
            }
            record.result = messageListeners.length;
            break;
        }
        default:
            throw new Error(`unknown scenario ${spec.scenario}`);
    }
    return record;
}

async function main() {
    const [modulePath, inputPath] = process.argv.slice(2);
    const input = JSON.parse(fs.readFileSync(inputPath, "utf-8"));
    const factorySource = moduleFactorySource(fs.readFileSync(modulePath, "utf-8"));
    const cases = {};
    for (const spec of input.cases) {
        try {
            cases[spec.name] = await runCase(factorySource, spec, input.vapidKey);
        } catch (error) {
            cases[spec.name] = {harnessError: String(error && error.stack)};
        }
    }
    process.stdout.write(JSON.stringify({cases}));
}

main().catch((error) => {
    process.stdout.write(JSON.stringify({harnessError: String(error && error.stack)}));
});
