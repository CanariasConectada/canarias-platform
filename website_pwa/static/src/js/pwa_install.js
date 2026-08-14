/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {registry} from "@web/core/registry";
import {Interaction} from "@web/public/interaction";

/**
 * Registers the service worker and drives the "install this app" card.
 *
 * The two platforms behave differently and the card reflects that instead of
 * pretending otherwise:
 *
 * - Android/Chrome fires `beforeinstallprompt` when it decides the site is
 *   installable. The event is captured, the default mini-infobar suppressed,
 *   and the button shown. Rendering the button before that event means
 *   offering an action the browser will refuse.
 * - iOS never fires it and exposes no API at all, so the card falls back to
 *   telling the visitor which menu to use.
 *
 * When the app is already installed both branches are pointless, so the card
 * stays hidden.
 */
export class PWAInstall extends Interaction {
    static selector = "#wrapwrap";

    setup() {
        this.deferredPrompt = null;
    }

    start() {
        this.registerServiceWorker();
        if (this.isStandalone()) {
            // Already running as an installed app: nothing to offer.
            return;
        }
        if (this.isIOS()) {
            this.revealCard(".o_pwa_ios_hint");
            return;
        }
        this.addListener(window, "beforeinstallprompt", (event) => {
            event.preventDefault();
            this.deferredPrompt = event;
            this.revealCard(".o_pwa_install_button");
        });
        this.addListener(document, "click", (event) => {
            const button = event.target.closest(".o_pwa_install_button");
            if (button) {
                this.promptInstall();
            }
        });
    }

    registerServiceWorker() {
        if (!("serviceWorker" in navigator)) {
            return;
        }
        // The manifest link is only rendered when the website has the app
        // enabled, so its absence is the signal to do nothing at all.
        if (!document.querySelector('link[rel="manifest"]')) {
            return;
        }
        navigator.serviceWorker.register("/service-worker.js", {scope: "/"});
    }

    isStandalone() {
        return (
            window.matchMedia("(display-mode: standalone)").matches ||
            window.navigator.standalone === true
        );
    }

    isIOS() {
        return /iphone|ipad|ipod/i.test(window.navigator.userAgent);
    }

    revealCard(childSelector) {
        const card = document.querySelector(".o_pwa_install_card");
        if (!card) {
            return;
        }
        card.classList.remove("d-none");
        const child = card.querySelector(childSelector);
        if (child) {
            child.classList.remove("d-none");
        }
    }

    async promptInstall() {
        if (!this.deferredPrompt) {
            return;
        }
        this.deferredPrompt.prompt();
        await this.deferredPrompt.userChoice;
        // The event can only be used once; drop it either way so a second
        // click does not call a spent prompt.
        this.deferredPrompt = null;
        const card = document.querySelector(".o_pwa_install_card");
        if (card) {
            card.classList.add("d-none");
        }
    }
}

registry.category("public.interactions").add("website_pwa.install", PWAInstall);
