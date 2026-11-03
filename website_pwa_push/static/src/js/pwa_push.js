/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {registry} from "@web/core/registry";
import {Interaction} from "@web/public/interaction";
import {rpc} from "@web/core/network/rpc";
import {user} from "@web/core/user";
import {PWAInstall} from "@website_pwa/js/pwa_install";

/**
 * Core's backend worker: the one `web`'s web client registers
 * (web/static/src/webclient/webclient.js, `registerServiceWorker`) and the
 * only one that carries core `mail`'s push handler -- and only when the
 * script is fetched by an INTERNAL user (mail/controllers/webmanifest.py).
 * Registering it with this exact URL and scope from a website page resolves
 * to the SAME registration the web client uses, never a second one.
 */
export const BACKEND_WORKER_URL = "/web/service-worker.js";
export const BACKEND_WORKER_SCOPE = "/odoo";

// The key core's web client keeps the last registered endpoint under
// (mail/static/src/webclient/web/webclient.js). Kept in step so the web
// client does not mistake our subscription for a lost one.
export const CORE_ENDPOINT_STORAGE_KEY = "mail.push.device_endpoint";

// "Not now" on the in-app prompt. Per device, and deliberately never sent to
// the server: it is a display preference, not a consent record.
const DISMISS_STORAGE_KEY = "website_pwa_push.prompt_dismissed";

// Per app session: a background refresh already ran for this target.
const SESSION_REFRESH_STORAGE_KEY = "website_pwa_push.refreshed";

/**
 * Which service worker a subscription made from this page must belong to.
 *
 * THE ROOT CAUSE THIS EXISTS FOR: an origin running the installed app has TWO
 * service workers. `/service-worker.js` (website_pwa, scope "/") controls the
 * website the app opens on; `/web/service-worker.js` (core, scope "/odoo")
 * controls the backend. A push is delivered to the worker of the registration
 * that owns the subscription, and only the handlers of THAT worker run. So:
 *
 * - "backend": an internal user. Core notifies them through the /odoo worker,
 *   whose handler knows calls, badges and the Discuss client. Subscribing
 *   them on the website worker would either display nothing (push off for the
 *   website) or display every message twice (once per worker).
 * - "deferred": an anonymous visitor on the login page. There is nobody to
 *   subscribe yet, but the permission prompt needs a user gesture (iOS will
 *   not show it otherwise), and after signing in core's web client subscribes
 *   on its own as soon as permission is already granted. So the click asks
 *   for permission now and the subscription follows the login.
 * - "website": a portal user or a guest on a website with push enabled; they
 *   never load the backend, so the website worker is theirs.
 *
 * @param {Object} persona
 * @param {boolean} persona.isInternalUser
 * @param {boolean} persona.isLoggedIn
 * @param {boolean} persona.websitePushEnabled
 * @param {boolean} persona.loginContext the card sits on a login/signup page
 * @returns {"backend"|"deferred"|"website"|null}
 */
export function pushTarget({isInternalUser, isLoggedIn, websitePushEnabled, loginContext}) {
    if (isInternalUser) {
        return "backend";
    }
    if (!isLoggedIn && loginContext) {
        return "deferred";
    }
    if (websitePushEnabled) {
        return "website";
    }
    return null;
}

/**
 * base64url string (what `/mail/push/vapid` returns) to the bytes
 * `pushManager.subscribe` wants. Same conversion core's web client does;
 * passing the string straight through is not accepted by every engine.
 */
export function base64UrlToUint8Array(value) {
    const padding = "=".repeat((4 - (value.length % 4)) % 4);
    const base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
    const raw = window.atob(base64);
    const output = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) {
        output[i] = raw.charCodeAt(i);
    }
    return output;
}

/** Unpadded base64url of an ArrayBuffer (the inverse, for comparisons). */
export function arrayBufferToBase64Url(buffer) {
    if (!buffer) {
        return "";
    }
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let i = 0; i < bytes.byteLength; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return window.btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

/**
 * Resolve once the registration has an active worker.
 *
 * `pushManager.subscribe` rejects on a registration without one, and a
 * registration made a moment ago usually has only an installing worker.
 */
export function whenActive(registration) {
    if (registration.active) {
        return Promise.resolve(registration);
    }
    const worker = registration.installing || registration.waiting;
    if (!worker) {
        // Nothing will ever fire a statechange: waiting would hang the card
        // forever. Only reachable when the browser dropped the worker between
        // `register` resolving and this call (an update that failed to
        // install, storage cleared meanwhile), so it gets its own message.
        console.warn(
            "PWA push: service worker registration has no worker to wait for",
            registration.scope
        );
        return Promise.reject(
            new Error("service worker registration has no installing, waiting or active worker")
        );
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

/**
 * Drives the notification cards: the "Activar avisos" snippet, the block on
 * the login page and the prompt shown inside the installed app.
 *
 * THE ONE RULE HERE: `Notification.requestPermission()` is called from the
 * click handler and from nowhere else. Asking on page load is not merely rude
 * -- Chrome counts unprompted requests as an abuse signal and can put the site
 * under a quieter permission UI for everybody, and Safari ignores a request
 * that does not come from a gesture, so the call would be a silent no-op that
 * also spends the visitor's only chance to say yes.
 *
 * Card options, as data attributes on `.o_pwa_push_card`:
 *
 * - `data-pwa-push-context="login"`: the card sits on an auth page, so an
 *   anonymous visitor is about to become somebody (see `pushTarget`).
 * - `data-pwa-push-standalone="1"`: only inside the installed app. Outside
 *   it the install block next to it is the right call to action.
 * - `data-pwa-push-prompt-only="1"`: only while permission has not been
 *   decided and the prompt was not dismissed on this device.
 */
export class PWAPush extends Interaction {
    static selector = ".o_pwa_push_card";

    dynamicContent = {
        ".o_pwa_push_button": {"t-on-click": () => this.onActivateClick()},
        ".o_pwa_push_dismiss": {"t-on-click": () => this.onDismissClick()},
    };

    setup() {
        this.target = pushTarget({
            isInternalUser: Boolean(user.isInternalUser),
            isLoggedIn: Boolean(user.userId),
            websitePushEnabled: this.isPushEnabledHere(),
            loginContext: this.el.dataset.pwaPushContext === "login",
        });
    }

    /**
     * Deliberately in `start` and not in `willStart`, and deliberately without
     * awaiting the refresh below: `willStart` is what the framework waits for
     * before the page is considered interactive, and this branch ends in a
     * service worker becoming active, which never happens when none was ever
     * registered. Blocking the page on that is not a risk worth taking.
     */
    start() {
        if (!this.target) {
            return;
        }
        const standalone = this.isStandalone();
        if (this.el.dataset.pwaPushStandalone && !standalone) {
            return;
        }
        // Checked BEFORE push support on purpose: Safari on iOS only exposes
        // PushManager and Notification inside an installed app, so a support
        // check first made this branch unreachable on every real iPhone.
        if (this.isIOS() && !standalone) {
            this.show(".o_pwa_push_ios_hint");
            return;
        }
        if (!this.isPushSupported()) {
            return;
        }
        if (this.el.dataset.pwaPushPromptOnly) {
            if (Notification.permission === "granted") {
                // Granted earlier -- typically on the login page, before
                // there was anybody to subscribe. Nothing to show, but the
                // subscription is made now rather than whenever the backend
                // happens to be opened. Once per app session: the server
                // row is idempotent, the round trips on every page are not.
                this.refreshOncePerSession();
                return;
            }
            if (Notification.permission !== "default" || this.isDismissed()) {
                return;
            }
        }
        if (Notification.permission === "denied") {
            this.show(".o_pwa_push_denied");
            return;
        }
        if (Notification.permission === "granted") {
            // Already said yes: no prompt, no button. The subscription is
            // re-registered in the background, because the server row can be
            // gone (a push service 404 unlinks it) while the browser still
            // holds the endpoint.
            this.showDone();
            this.subscribe();
            return;
        }
        this.show(".o_pwa_push_button");
    }

    /**
     * Is push enabled for THIS website?
     *
     * The meta tag is emitted by the layout when `pwa_push_enabled` is on,
     * which is also the condition under which the website worker carries push
     * handlers -- so without it a portal user or guest could be talked into
     * granting permission for notifications that would never be displayed.
     * Internal users do not depend on it: their pushes go through core's
     * backend worker, whatever the website switch says.
     */
    isPushEnabledHere() {
        return Boolean(document.querySelector('meta[name="cc-pwa-push"]'));
    }

    /**
     * Reads the three APIs rather than testing for their names: an `in`
     * check is true for an accessor that throws when read (some privacy
     * modes and in-app browsers do exactly that), and the first real use
     * would then throw out of `start`.
     */
    isPushSupported() {
        try {
            return Boolean(
                navigator.serviceWorker && window.PushManager && window.Notification
            );
        } catch {
            return false;
        }
    }

    /**
     * Platform detection, borrowed rather than rewritten, so the install card
     * and this card can never contradict each other on the same page.
     */
    isIOS() {
        return PWAInstall.prototype.isIOS.call(this);
    }

    isStandalone() {
        return PWAInstall.prototype.isStandalone.call(this);
    }

    isDismissed() {
        try {
            return Boolean(window.localStorage.getItem(DISMISS_STORAGE_KEY));
        } catch {
            return false;
        }
    }

    show(selector) {
        this.el.classList.remove("d-none");
        const branch = this.el.querySelector(selector);
        if (branch) {
            branch.classList.remove("d-none");
        }
    }

    hide(selector) {
        const branch = this.el.querySelector(selector);
        if (branch) {
            branch.classList.add("d-none");
        }
    }

    showDone() {
        // A login page confirms something different: permission is granted,
        // but the notifications start once the visitor signs in.
        if (this.target === "deferred" && this.el.querySelector(".o_pwa_push_deferred")) {
            this.show(".o_pwa_push_deferred");
        } else {
            this.show(".o_pwa_push_done");
        }
    }

    refreshOncePerSession() {
        const key = `${SESSION_REFRESH_STORAGE_KEY}.${this.target}`;
        try {
            if (window.sessionStorage.getItem(key)) {
                return;
            }
            window.sessionStorage.setItem(key, "1");
        } catch {
            // No storage: refreshing on every page is still correct.
        }
        this.subscribe();
    }

    onDismissClick() {
        try {
            window.localStorage.setItem(DISMISS_STORAGE_KEY, "1");
        } catch {
            // Private mode: the prompt simply comes back next time.
        }
        this.el.classList.add("d-none");
    }

    /**
     * The gesture. `requestPermission` is the first thing this does, on
     * purpose: Safari drops the user-activation as soon as an await lands
     * before it.
     */
    async onActivateClick() {
        const permission = await this.waitFor(Notification.requestPermission());
        this.hide(".o_pwa_push_button");
        if (permission !== "granted") {
            // "default" means the visitor dismissed the prompt. Not an error
            // and not a reason to ask again: the card simply stops offering.
            if (permission === "denied") {
                this.show(".o_pwa_push_denied");
            }
            return;
        }
        const subscribed = await this.subscribe();
        if (subscribed) {
            this.showDone();
        }
    }

    /**
     * The registration a subscription from this page belongs to.
     *
     * "backend": the /odoo registration, registered here if the web client
     * never ran in this app yet -- same URL and scope, so the same one.
     * "website": the registration controlling this page; `ready` rather than
     * `register` because registering the website worker is website_pwa's job
     * and doing it twice would race with it.
     */
    async pushRegistration() {
        if (this.target === "backend") {
            const registration = await navigator.serviceWorker.register(
                BACKEND_WORKER_URL,
                {scope: BACKEND_WORKER_SCOPE}
            );
            return whenActive(registration);
        }
        return navigator.serviceWorker.ready;
    }

    /**
     * Retire a subscription this browser still holds on the WEBSITE worker.
     *
     * An internal user may have been subscribed there before this module
     * routed them to the backend worker (or on a website with push on). With
     * both alive every message arrives twice, once per worker. The browser
     * side is unsubscribed and the server row removed through the public
     * route, which only removes rows owned by the caller.
     *
     * `getRegistration("/")` answers the registration whose scope matches the
     * site root, which can only be the website worker: "/odoo" does not
     * match "/". Best effort: a failure here must not undo the backend
     * subscription that just succeeded.
     */
    async dropWebsiteSubscription(backendEndpoint) {
        try {
            const registration = await this.waitFor(
                navigator.serviceWorker.getRegistration("/")
            );
            if (!registration) {
                return;
            }
            const subscription = await this.waitFor(
                registration.pushManager.getSubscription()
            );
            if (!subscription || subscription.endpoint === backendEndpoint) {
                return;
            }
            const endpoint = subscription.endpoint;
            await this.waitFor(subscription.unsubscribe());
            await this.waitFor(rpc("/mail/push/unsubscribe", {endpoint: endpoint}));
        } catch (error) {
            console.warn("PWA push: could not retire the website subscription", error);
        }
    }

    /**
     * Subscribe this browser and hand the subscription to the server.
     *
     * @returns {Promise<boolean>} whether the server accepted a subscription
     *   (always true for "deferred": there is nothing to send until login)
     */
    async subscribe() {
        if (this.target === "deferred") {
            return true;
        }
        let key = false;
        try {
            const result = await this.waitFor(rpc("/mail/push/vapid"));
            key = result && result.vapid_public_key;
        } catch (error) {
            // The route answers `false` when no key pair exists yet; anything
            // else here is a server error. Either way there is nothing to
            // subscribe with, and nothing worth putting in the visitor's face.
            console.warn("PWA push: no VAPID key available", error);
            return false;
        }
        if (!key) {
            return false;
        }
        try {
            const registration = await this.waitFor(this.pushRegistration());
            let subscription = await this.waitFor(
                registration.pushManager.getSubscription()
            );
            // A subscription made with a rotated key pair can never be
            // encrypted for. Registering it would be registering a device that
            // silently receives nothing, so it is replaced instead.
            const subscribedKey =
                subscription &&
                arrayBufferToBase64Url(subscription.options.applicationServerKey);
            if (subscription && subscribedKey && subscribedKey !== key) {
                await this.waitFor(subscription.unsubscribe());
                subscription = null;
            }
            if (!subscription) {
                subscription = await this.waitFor(
                    registration.pushManager.subscribe({
                        // Required by Chrome, and a promise both workers keep:
                        // every push shows a notification.
                        userVisibleOnly: true,
                        applicationServerKey: base64UrlToUint8Array(key),
                    })
                );
                if (this.target === "backend") {
                    try {
                        window.localStorage.setItem(
                            CORE_ENDPOINT_STORAGE_KEY,
                            subscription.endpoint
                        );
                    } catch {
                        // Only bookkeeping for core's web client.
                    }
                }
            }
            const {endpoint, keys, expirationTime} = subscription.toJSON();
            await this.waitFor(
                rpc("/mail/push/subscribe", {
                    endpoint: endpoint,
                    keys: keys,
                    expiration_time: expirationTime,
                    vapid_public_key: key,
                    // Which worker owns the subscription. The server keeps it
                    // on the device row so it can drop an internal user's
                    // leftover website-worker devices (mail_push_guest).
                    worker: this.target,
                })
            );
            if (this.target === "backend") {
                await this.dropWebsiteSubscription(endpoint);
            }
            return true;
        } catch (error) {
            console.warn("PWA push: subscription failed", error);
            return false;
        }
    }
}

/**
 * Where core's backend worker wants a tapped notification to go.
 *
 * Returns null for anything that is not a positive integer id: the message
 * comes from our own origin's worker, but the id ends up in a URL.
 */
export function discussChannelUrl(channelId, joinCall = false) {
    const id = Number(channelId);
    if (!Number.isInteger(id) || id <= 0) {
        return null;
    }
    const url = new URL("/odoo/action-mail.action_discuss", window.location.origin);
    url.searchParams.set("active_id", `discuss.channel_${id}`);
    if (joinCall) {
        url.searchParams.set("call", "accept");
    }
    return url.pathname + url.search;
}

/**
 * Opens the conversation when a notification is tapped while the installed
 * app is showing the WEBSITE.
 *
 * Core's backend worker (mail/static/src/service_worker.js,
 * `openDiscussChannel`) does not open a window when one already exists: it
 * picks an open window -- any window of the origin, the website included --
 * posts it `OPEN_CHANNEL` and focuses it, trusting the Discuss client in that
 * window to open the channel. An installed app has exactly one window, and
 * when it is on the website there is no Discuss client in it, so the tap
 * brought the app to the front and nothing else happened. This is the
 * listener that was missing on that side.
 */
export class PWAPushOpenChannel extends Interaction {
    static selector = "#wrapwrap";

    start() {
        let container = null;
        try {
            container = navigator.serviceWorker;
        } catch {
            // Some privacy modes and embedded browsers make the accessor
            // itself throw. No worker, so no message to wait for.
        }
        if (!container) {
            return;
        }
        this.addListener(container, "message", (event) => this.onWorkerMessage(event));
        // Messages posted before the listener existed are queued until this.
        container.startMessages?.();
    }

    onWorkerMessage({data}) {
        if (!data || data.action !== "OPEN_CHANNEL" || !data.data) {
            return;
        }
        const url = discussChannelUrl(data.data.id, data.data.joinCall);
        if (url) {
            window.location.assign(url);
        }
    }
}

registry.category("public.interactions").add("website_pwa_push.push", PWAPush);
registry
    .category("public.interactions")
    .add("website_pwa_push.open_channel", PWAPushOpenChannel);
