/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {Component, onMounted, onWillUnmount, useState} from "@odoo/owl";
import {DiscussClientAction} from "@mail/core/public_web/discuss_client_action";
import {browser} from "@web/core/browser/browser";
import {isDisplayStandalone, isIOS} from "@web/core/browser/feature_detection";
import {rpc} from "@web/core/network/rpc";
import {patch} from "@web/core/utils/patch";

/** sessionStorage key: dismissed for this browser session only. */
export const BANNER_DISMISSED_KEY = "discuss_community.notification_banner_dismissed";

/**
 * Core's backend worker (web/static/src/webclient/webclient.js,
 * `registerServiceWorker`): the only one carrying core `mail`'s push handler.
 * Registering the same URL and scope resolves to the SAME registration the
 * web client uses, never a second one.
 */
export const BACKEND_WORKER_URL = "/web/service-worker.js";
export const BACKEND_WORKER_SCOPE = "/odoo";

/** Where core's web client keeps the last registered endpoint. */
export const CORE_ENDPOINT_STORAGE_KEY = "mail.push.device_endpoint";

/** Answers of `mail.push.device.cc_push_status` (mail_push_guest). */
export const STATUS_REGISTERED = "registered";
export const STATUS_NOT_REGISTERED = "not_registered";
export const STATUS_OWNED_BY_OTHER = "owned_by_other";

/** How long the success message stays before the banner hides itself. */
export const SUCCESS_HIDE_DELAY_MS = 6000;

/**
 * Banner phases:
 * - "checking": first silent validation still running; nothing shown.
 * - "hidden": this device is registered for this user; nothing shown.
 * - "inactive": not active yet (reason: no_permission, no_subscription,
 *   not_registered, owned_by_other); offers "Activate and verify".
 * - "working": activation running.
 * - "success": verified, a test push was requested; hides itself.
 * - "error": activation failed (reason: denied, owned_by_other,
 *   unsupported, unsupported_ios, no_key, not_stored, server), with the
 *   next step to take.
 */
function state(phase, reason = null, message = "") {
    return {phase, reason, message};
}

/** base64url (VAPID public key) to the bytes `pushManager.subscribe` wants. */
export function base64UrlToUint8Array(value) {
    const padding = "=".repeat((4 - (value.length % 4)) % 4);
    const base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
    const raw = globalThis.atob(base64);
    const output = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) {
        output[i] = raw.charCodeAt(i);
    }
    return output;
}

/** Unpadded base64url of an ArrayBuffer (to compare subscription keys). */
export function arrayBufferToBase64Url(buffer) {
    if (!buffer) {
        return "";
    }
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let i = 0; i < bytes.byteLength; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return globalThis.btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

/** Resolve once the registration has an active worker. */
export function whenActive(registration) {
    if (registration.active) {
        return Promise.resolve(registration);
    }
    const worker = registration.installing || registration.waiting;
    if (!worker) {
        return Promise.reject(new Error("service worker registration has no worker"));
    }
    return new Promise((resolve, reject) => {
        worker.addEventListener("statechange", () => {
            if (worker.state === "activated") {
                resolve(registration);
            } else if (worker.state === "redundant") {
                reject(new Error("service worker became redundant"));
            }
        });
    });
}

function errorMessage(error) {
    return (error && (error.data?.message || error.message)) || String(error);
}

/**
 * The state machine behind the banner: VALIDATES that this device is really
 * registered for the current user instead of trusting the browser
 * permission.
 *
 * WHY: every registration door on the server is silent on refusal (see
 * mail_push_guest `_may_claim_device`), and core's door returns None
 * whatever happened. Production incident of 2026-09-26: an iPhone had the
 * permission and a subscription, the banner hid because permission was
 * "granted", and the server held no device for that user.
 *
 * Framework-free on purpose (every browser API comes in through `env`), so
 * `tests/test_notification_banner_js.py` can run it in node.
 *
 * @param {Object} env
 * @param {Object} env.navigator
 * @param {Object} env.Notification the Notification constructor, or undefined
 * @param {Function} env.PushManager or undefined
 * @param {Function} env.rpc (url, params) => Promise
 * @param {Object} env.localStorage
 * @param {Function} env.isIOS
 * @param {Function} env.isStandalone
 */
export class PushValidator {
    constructor(env) {
        this.env = env;
    }

    /** "ok", "unsupported" or "unsupported_ios" (Safari outside the app). */
    support() {
        let supported = false;
        try {
            supported = Boolean(
                this.env.navigator.serviceWorker && this.env.PushManager && this.env.Notification
            );
        } catch {
            supported = false;
        }
        if (supported) {
            return "ok";
        }
        // iOS only exposes the Push API to an app installed from the home
        // screen (iOS 16.4+): the one case with a concrete next step.
        return this.env.isIOS() && !this.env.isStandalone() ? "unsupported_ios" : "unsupported";
    }

    callKw(method, kwargs = {}) {
        return this.env.rpc(`/web/dataset/call_kw/mail.push.device/${method}`, {
            model: "mail.push.device",
            method,
            args: [],
            kwargs,
        });
    }

    status(endpoint) {
        return this.callKw("cc_push_status", {endpoint});
    }

    /**
     * Silent validation, on every Discuss load. Never prompts.
     *
     * @returns {Promise<{phase, reason, message}>}
     */
    async check() {
        const support = this.support();
        if (support !== "ok") {
            return state("error", support);
        }
        const permission = this.env.Notification.permission;
        if (permission === "denied") {
            return state("error", "denied");
        }
        if (permission !== "granted") {
            return state("inactive", "no_permission");
        }
        try {
            const registration = await this.env.navigator.serviceWorker.getRegistration(
                BACKEND_WORKER_SCOPE
            );
            const subscription =
                registration && (await registration.pushManager.getSubscription());
            if (!subscription) {
                return state("inactive", "no_subscription");
            }
            const status = await this.status(subscription.endpoint);
            if (status === STATUS_REGISTERED) {
                return state("hidden");
            }
            if (status === STATUS_OWNED_BY_OTHER) {
                return state("inactive", "owned_by_other");
            }
            return state("inactive", "not_registered");
        } catch (error) {
            return state("error", "server", errorMessage(error));
        }
    }

    async vapidKey() {
        const result = await this.env.rpc("/mail/push/vapid", {});
        if (result && result.vapid_public_key) {
            return result.vapid_public_key;
        }
        // No key pair yet: only an administrator may generate it
        // (mail_push_guest `get_web_push_vapid_public_key`).
        return this.callKw("get_web_push_vapid_public_key");
    }

    async backendRegistration() {
        const registration = await this.env.navigator.serviceWorker.register(
            BACKEND_WORKER_URL,
            {scope: BACKEND_WORKER_SCOPE}
        );
        return whenActive(registration);
    }

    /** The current subscription, replaced when made with another key. */
    async ensureSubscription(registration, key) {
        let subscription = await registration.pushManager.getSubscription();
        if (subscription) {
            const subscribedKey = arrayBufferToBase64Url(
                subscription.options && subscription.options.applicationServerKey
            );
            if (subscribedKey && subscribedKey !== key) {
                await subscription.unsubscribe();
                subscription = null;
            }
        }
        if (!subscription) {
            subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: base64UrlToUint8Array(key),
            });
        }
        return subscription;
    }

    async register(subscription, key) {
        const {endpoint, keys, expirationTime} = subscription.toJSON();
        await this.env.rpc("/mail/push/subscribe", {
            endpoint,
            keys,
            expiration_time: expirationTime,
            vapid_public_key: key,
            worker: "backend",
        });
        try {
            // Keeps core's web client from sending a stale previousEndpoint.
            this.env.localStorage.setItem(CORE_ENDPOINT_STORAGE_KEY, endpoint);
        } catch {
            // Only bookkeeping for core's web client.
        }
    }

    /**
     * "Activate and verify". MUST be called straight from the click handler:
     * `requestPermission` is its first await, because iOS only shows the
     * prompt inside a user gesture.
     *
     * @returns {Promise<{phase, reason, message}>}
     */
    async activate() {
        const support = this.support();
        if (support !== "ok") {
            return state("error", support);
        }
        let permission;
        try {
            permission = await this.env.Notification.requestPermission();
        } catch {
            permission = this.env.Notification.permission;
        }
        if (permission === "denied") {
            return state("error", "denied");
        }
        if (permission !== "granted") {
            return state("inactive", "no_permission");
        }
        try {
            const registration = await this.backendRegistration();
            const key = await this.vapidKey();
            if (!key) {
                return state("error", "no_key");
            }
            let subscription = await this.ensureSubscription(registration, key);
            await this.register(subscription, key);
            let status = await this.status(subscription.endpoint);
            if (status === STATUS_OWNED_BY_OTHER) {
                // This browser proves possession: it holds the subscription.
                // Dropping it and subscribing again yields a NEW endpoint,
                // which nobody owns, without touching the other account's
                // row (it dies at the push service's next 404/410).
                await subscription.unsubscribe();
                subscription = await this.ensureSubscription(registration, key);
                await this.register(subscription, key);
                status = await this.status(subscription.endpoint);
            }
            if (status === STATUS_OWNED_BY_OTHER) {
                return state("error", "owned_by_other");
            }
            if (status !== STATUS_REGISTERED) {
                return state("error", "not_stored");
            }
            const test = await this.callKw("cc_push_test");
            return state("success", test && test.status === "sent" ? "tested" : null);
        } catch (error) {
            return state("error", "server", errorMessage(error));
        }
    }
}

function readDismissed() {
    try {
        return browser.sessionStorage.getItem(BANNER_DISMISSED_KEY) === "1";
    } catch {
        return false;
    }
}

function browserEnv() {
    return {
        navigator: browser.navigator,
        Notification: browser.Notification,
        PushManager: globalThis.PushManager,
        rpc,
        localStorage: browser.localStorage,
        isIOS,
        isStandalone: isDisplayStandalone,
    };
}

/**
 * "Notifications are not active on this device" banner at the top of
 * Discuss, for everybody (guests, merchants, staff).
 *
 * Re-validated silently on every Discuss load: shown whenever this device is
 * not registered for this user on the server, whatever the browser
 * permission says. Closing it hides it for the browser session only.
 */
export class DiscussNotificationBanner extends Component {
    static template = "discuss_community.DiscussNotificationBanner";
    static props = {};

    setup() {
        this.validator = new PushValidator(browserEnv());
        this.state = useState({...state("checking"), dismissed: readDismissed()});
        onMounted(() => this.revalidate());
        onWillUnmount(() => browser.clearTimeout(this.hideTimer));
    }

    get isVisible() {
        return (
            !this.state.dismissed &&
            ["inactive", "working", "success", "error"].includes(this.state.phase)
        );
    }

    get canActivate() {
        const {phase, reason} = this.state;
        if (phase === "inactive") {
            return true;
        }
        return phase === "error" && ["owned_by_other", "server", "not_stored"].includes(reason);
    }

    get alertClass() {
        switch (this.state.phase) {
            case "success":
                return "alert-success";
            case "error":
                return "alert-warning";
            default:
                return "alert-info";
        }
    }

    apply(result) {
        Object.assign(this.state, result);
    }

    async revalidate() {
        const result = await this.validator.check();
        // An activation started meanwhile owns the banner.
        if (this.state.phase === "checking") {
            this.apply(result);
        }
    }

    async onClickActivate() {
        // No await before `activate`: it must start inside the gesture.
        const pending = this.validator.activate();
        this.apply(state("working"));
        const result = await pending;
        this.apply(result);
        if (result.phase === "success") {
            browser.clearTimeout(this.hideTimer);
            this.hideTimer = browser.setTimeout(
                () => this.apply(state("hidden")),
                SUCCESS_HIDE_DELAY_MS
            );
        }
    }

    onClickDismiss() {
        this.state.dismissed = true;
        try {
            browser.sessionStorage.setItem(BANNER_DISMISSED_KEY, "1");
        } catch {
            // Storage unavailable (private mode): hidden until reload.
        }
    }
}

patch(DiscussClientAction, {
    components: {...DiscussClientAction.components, DiscussNotificationBanner},
});
