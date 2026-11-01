/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
 *
 * Runs the Discuss notification banner's state machine
 * (static/src/backend/notification_banner.js, class PushValidator and the
 * component around it) outside a browser, against fakes of the Push API and
 * of the server RPCs.
 *
 * Only drives and observes; every assertion lives in Python
 * (test_notification_banner_js.py). The module is the shipped file with its
 * ES `import`/`export` keywords stripped and its framework imports replaced
 * by stubs.
 *
 * Usage:  node notification_banner_harness.js <notification_banner.js> <input.json>
 * stdout: a single JSON object {"cases": {<name>: <observations>}}.
 */
"use strict";

const fs = require("fs");

// Timers armed through the stubbed `browser.setTimeout`, reset per case.
let TIMERS = [];

const EXPORTED = [
    "PushValidator",
    "DiscussNotificationBanner",
    "BACKEND_WORKER_URL",
    "BACKEND_WORKER_SCOPE",
    "CORE_ENDPOINT_STORAGE_KEY",
    "SUCCESS_HIDE_DELAY_MS",
];

function moduleFactory(source) {
    const body = source
        .split("\n")
        .filter((line) => !/^import\s/.test(line))
        .join("\n")
        .replace(/^export\s+(?=(async\s+)?(class|function|const)\b)/gm, "");
    // eslint-disable-next-line no-new-func
    return new Function(
        "deps",
        `const {Component, onMounted, onWillUnmount, useState, DiscussClientAction,
                browser, isDisplayStandalone, isIOS, rpc, patch} = deps;
        ${body}
        return {${EXPORTED.join(", ")}};`
    );
}

function bytesToBuffer(bytes) {
    return Uint8Array.from(bytes).buffer;
}

function makeEnv(input, spec, log) {
    const server = spec.server || {};
    const statusQueue = {...(server.status || {})};
    const endpoints = [...(spec.newEndpoints || [])];
    const storage = {};

    function makeSubscription(endpoint, keyBytes) {
        return {
            endpoint,
            options: {applicationServerKey: keyBytes ? bytesToBuffer(keyBytes) : null},
            toJSON() {
                return {
                    endpoint,
                    expirationTime: null,
                    keys: {p256dh: "p256dh-" + endpoint, auth: "auth"},
                };
            },
            async unsubscribe() {
                log.push("unsubscribe:" + endpoint);
                registration.subscription = null;
                return true;
            },
        };
    }

    const registration = {
        active: {state: "activated"},
        subscription: spec.subscription
            ? makeSubscription(spec.subscription.endpoint, spec.subscription.keyBytes)
            : null,
        pushManager: {
            async getSubscription() {
                return registration.subscription;
            },
            async subscribe(options) {
                const endpoint = endpoints.shift();
                log.push("subscribe:" + endpoint);
                if (!endpoint) {
                    throw new Error("push service refused");
                }
                registration.subscription = makeSubscription(
                    endpoint,
                    Array.from(options.applicationServerKey)
                );
                return registration.subscription;
            },
        },
    };

    const support = spec.support || {};
    const navigator = {};
    if (support.serviceWorker !== false) {
        navigator.serviceWorker = {
            async getRegistration(scope) {
                log.push("getRegistration:" + scope);
                return spec.registered === false ? undefined : registration;
            },
            async register(url, options) {
                log.push(`register:${url}|${options.scope}`);
                return registration;
            },
        };
    }
    let Notification;
    if (support.Notification !== false) {
        Notification = {
            permission: spec.permission || "default",
            async requestPermission() {
                log.push("requestPermission");
                Notification.permission = spec.grant || Notification.permission;
                return Notification.permission;
            },
        };
    }

    async function rpc(route, params) {
        const method = params && params.method;
        const label = method ? `rpc:${method}` : `rpc:${route}`;
        log.push(label);
        // `failOnce`: a list of messages, one consumed per call, then the
        // call succeeds (a transient conflict).
        const transient = (server.failOnce || {})[method || route];
        if (transient && transient.length) {
            const message = transient.shift();
            const error = new Error(message);
            error.data = {message};
            throw error;
        }
        const failing = (server.fail || {})[method || route];
        if (failing) {
            const error = new Error(failing);
            error.data = {message: failing};
            throw error;
        }
        if (route === "/mail/push/vapid") {
            return {vapid_public_key: server.vapidRoute === false ? false : input.vapidKey};
        }
        if (method === "get_web_push_vapid_public_key") {
            return server.vapidOrm || false;
        }
        if (route === "/mail/push/subscribe") {
            log.push("subscribed-endpoint:" + params.endpoint + "|" + params.worker);
            return true;
        }
        if (method === "cc_push_status") {
            const answers = statusQueue[params.kwargs.endpoint];
            if (Array.isArray(answers)) {
                return answers.length > 1 ? answers.shift() : answers[0];
            }
            return answers || "not_registered";
        }
        if (method === "cc_push_test") {
            return server.test || {status: "sent", devices: 1};
        }
        throw new Error("unexpected rpc " + route);
    }

    return {
        storage,
        env: {
            navigator,
            Notification,
            PushManager: support.PushManager === false ? undefined : function PushManager() {},
            rpc,
            localStorage: {
                setItem(key, value) {
                    storage[key] = value;
                },
            },
            isIOS: () => Boolean(spec.ios),
            isStandalone: () => Boolean(spec.standalone),
            sleep(ms) {
                log.push("sleep:" + ms);
                return Promise.resolve();
            },
        },
    };
}

async function runCase(mod, input, spec) {
    const log = [];
    const {env, storage} = makeEnv(input, spec, log);
    const validator = new mod.PushValidator(env);
    let result;
    if (spec.action === "check") {
        result = await validator.check();
    } else if (spec.action === "activate") {
        result = await validator.activate();
    } else if (spec.action === "component") {
        // The component, with OWL replaced by plain objects and a manual
        // clock, to observe the phases it walks through on a click.
        const timers = TIMERS;
        const component = Object.create(mod.DiscussNotificationBanner.prototype);
        component.validator = validator;
        component.state = {phase: "inactive", reason: "no_permission", message: "", dismissed: false};
        const clickPromise = component.onClickActivate();
        const phaseRightAfterClick = component.state.phase;
        const logRightAfterClick = [...log];
        await clickPromise;
        const phaseAfter = component.state.phase;
        const visibleAfter = component.isVisible;
        const delays = timers.map((timer) => timer.delay);
        timers.forEach((timer) => timer.fn());
        result = {
            phaseRightAfterClick,
            logRightAfterClick,
            phaseAfter,
            visibleAfter,
            delays,
            phaseAfterTimer: component.state.phase,
            visibleAfterTimer: component.isVisible,
        };
    }
    return {log, storage, result};
}

async function main() {
    const [scriptPath, inputPath] = process.argv.slice(2);
    const input = JSON.parse(fs.readFileSync(inputPath, "utf-8"));
    const output = {cases: {}};
    let mod;
    try {
        const deps = {
            Component: class {},
            onMounted() {},
            onWillUnmount() {},
            useState: (value) => value,
            DiscussClientAction: {components: {}},
            browser: {
                sessionStorage: {getItem: () => null, setItem() {}},
                setTimeout(fn, delay) {
                    TIMERS.push({fn, delay});
                    return TIMERS.length;
                },
                clearTimeout() {},
            },
            isDisplayStandalone: () => false,
            isIOS: () => false,
            rpc: () => Promise.reject(new Error("unused")),
            patch() {},
        };
        mod = moduleFactory(fs.readFileSync(scriptPath, "utf-8"))(deps);
        output.constants = {
            url: mod.BACKEND_WORKER_URL,
            scope: mod.BACKEND_WORKER_SCOPE,
            storageKey: mod.CORE_ENDPOINT_STORAGE_KEY,
        };
    } catch (error) {
        process.stdout.write(JSON.stringify({harnessError: String(error.stack || error)}));
        return;
    }
    for (const spec of input.cases) {
        try {
            TIMERS = [];
            const observed = await runCase(mod, input, spec);
            output.cases[spec.name] = observed;
        } catch (error) {
            output.cases[spec.name] = {harnessError: String(error.stack || error)};
        }
    }
    process.stdout.write(JSON.stringify(output));
}

main();
