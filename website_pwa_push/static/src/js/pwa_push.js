/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {registry} from "@web/core/registry";
import {Interaction} from "@web/public/interaction";
import {rpc} from "@web/core/network/rpc";
import {PWAInstall} from "@website_pwa/js/pwa_install";

/**
 * Drives the "Activar avisos" card.
 *
 * THE ONE RULE HERE: `Notification.requestPermission()` is called from the
 * click handler and from nowhere else. Asking on page load is not merely rude
 * -- Chrome counts unprompted requests as an abuse signal and can put the site
 * under a quieter permission UI for everybody, and Safari ignores a request
 * that does not come from a gesture, so the call would be a silent no-op that
 * also spends the visitor's only chance to say yes.
 *
 * Everything else is deciding WHICH of the card's branches to show, and that
 * depends on things only the browser knows:
 *
 * - push unsupported (no service worker, no PushManager): nothing is shown.
 *   There is no honest button to offer.
 * - permission already "denied": the browser will not ask again, so the button
 *   would do nothing. The card explains where the setting lives instead.
 * - permission already "granted": no prompt is needed, so the subscription is
 *   refreshed silently and the card only confirms it. Asking again would be
 *   nagging somebody who already said yes.
 * - iOS outside an installed app: Safari refuses `pushManager.subscribe`
 *   anywhere but a PWA on the home screen, so the visitor gets the install
 *   instructions rather than a button that cannot work.
 */
export class PWAPush extends Interaction {
    static selector = ".o_pwa_push_card";

    dynamicContent = {
        ".o_pwa_push_button": {"t-on-click": () => this.onActivateClick()},
    };

    /**
     * Deliberately in `start` and not in `willStart`, and deliberately without
     * awaiting the refresh below: `willStart` is what the framework waits for
     * before the page is considered interactive, and this branch ends in
     * `navigator.serviceWorker.ready`, a promise that never settles when no
     * worker was ever registered. Blocking the page on that is not a risk
     * worth taking for a card in the footer.
     */
    start() {
        if (!this.isPushEnabledHere() || !this.isPushSupported()) {
            return;
        }
        if (this.isIOS() && !this.isStandalone()) {
            this.show(".o_pwa_push_ios_hint");
            return;
        }
        if (Notification.permission === "denied") {
            this.show(".o_pwa_push_denied");
            return;
        }
        if (Notification.permission === "granted") {
            // Already said yes: no prompt, no button. The subscription this
            // browser holds is re-registered in the background, because the
            // server row can be gone (a push service 404 unlinks it) while the
            // browser still holds the endpoint.
            this.show(".o_pwa_push_done");
            this.subscribe();
            return;
        }
        this.show(".o_pwa_push_button");
    }

    /**
     * Is push enabled for THIS website?
     *
     * The manifest link only says the app is enabled. The meta tag is emitted
     * by the layout when `pwa_push_enabled` is on, which is also the condition
     * under which the service worker carries push handlers -- so without it a
     * visitor could be talked into granting permission for notifications that
     * would never be displayed.
     */
    isPushEnabledHere() {
        return Boolean(document.querySelector('meta[name="cc-pwa-push"]'));
    }

    isPushSupported() {
        return (
            "serviceWorker" in navigator &&
            "PushManager" in window &&
            "Notification" in window
        );
    }

    /**
     * iOS detection, borrowed rather than rewritten.
     *
     * `website_pwa` already decides what "this is an iPhone" and "this is
     * running as an installed app" mean, and the two modules must not drift
     * apart: the install card and this card contradicting each other on the
     * same page is worse than either being wrong. Neither method touches its
     * instance, so calling it on ours is safe, and any future fix over there
     * (iPadOS reporting itself as a Mac, for instance) arrives here for free.
     */
    isIOS() {
        return PWAInstall.prototype.isIOS.call(this);
    }

    isStandalone() {
        return PWAInstall.prototype.isStandalone.call(this);
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
            this.show(".o_pwa_push_done");
        }
    }

    /**
     * Subscribe this browser and hand the subscription to the server.
     *
     * @returns {Promise<boolean>} whether the server accepted a subscription
     */
    async subscribe() {
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
            // `ready` and not `register`: registering the worker is
            // website_pwa's job, and doing it here too would race with it.
            const registration = await this.waitFor(navigator.serviceWorker.ready);
            const subscription =
                (await registration.pushManager.getSubscription()) ||
                (await registration.pushManager.subscribe({
                    // Required by Chrome, and a promise the worker keeps: every
                    // push shows a notification.
                    userVisibleOnly: true,
                    applicationServerKey: key,
                }));
            const {endpoint, keys, expirationTime} = subscription.toJSON();
            await this.waitFor(
                rpc("/mail/push/subscribe", {
                    endpoint: endpoint,
                    keys: keys,
                    expiration_time: expirationTime,
                    // Echoed back so a browser still holding a subscription
                    // from a rotated key pair is refused instead of registering
                    // a device nothing can ever encrypt for.
                    vapid_public_key: key,
                })
            );
            return true;
        } catch (error) {
            console.warn("PWA push: subscription failed", error);
            return false;
        }
    }
}

registry.category("public.interactions").add("website_pwa_push.push", PWAPush);
