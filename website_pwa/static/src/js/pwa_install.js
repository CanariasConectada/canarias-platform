/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {registry} from "@web/core/registry";
import {Interaction} from "@web/public/interaction";

/**
 * Is the page running as an installed app (home-screen launch)?
 *
 * Exported on its own so every card that must behave differently inside the
 * app -- the install card, the notification prompt, the login page block --
 * asks the same question the same way.
 */
export function isStandalone() {
    return (
        window.matchMedia("(display-mode: standalone)").matches ||
        window.navigator.standalone === true
    );
}

/**
 * Is this an iPhone, iPod or iPad?
 *
 * iPadOS 13+ reports itself as desktop Safari on a Mac ("Macintosh" in the
 * user agent, "MacIntel" as platform), so the user agent alone sends every
 * iPad down the Android branch: waiting for a `beforeinstallprompt` Safari
 * never fires, and no instructions shown. A Mac has no touch points; an iPad
 * has five.
 */
export function isIOS() {
    const nav = window.navigator;
    if (/iphone|ipad|ipod/i.test(nav.userAgent)) {
        return true;
    }
    return nav.platform === "MacIntel" && nav.maxTouchPoints > 1;
}

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
        // Installed from the browser menu rather than from our button: the
        // card must not keep offering what is already on the home screen.
        this.addListener(window, "appinstalled", () => this.hideCards());
        this.addListener(document, "click", (event) => {
            const button = event.target.closest(".o_pwa_install_button");
            if (button) {
                this.promptInstall();
            }
        });
    }

    registerServiceWorker() {
        // The manifest link is only rendered when the website has the app
        // enabled, so its absence is the signal to do nothing at all.
        if (!document.querySelector('link[rel="manifest"]')) {
            return;
        }
        // Never let the app plumbing break the page it sits on (the login
        // page first of all): the accessor can throw in some privacy modes,
        // and a refused registration must not surface as an unhandled
        // rejection.
        try {
            if (!navigator.serviceWorker) {
                return;
            }
            navigator.serviceWorker
                .register("/service-worker.js", {scope: "/"})
                .catch((error) => console.warn("PWA: service worker not registered", error));
        } catch (error) {
            console.warn("PWA: service workers unavailable", error);
        }
    }

    isStandalone() {
        return isStandalone();
    }

    isIOS() {
        return isIOS();
    }

    /**
     * Reveal EVERY install card on the page, not only the first.
     *
     * A page can carry more than one: the editor snippet and the login page's
     * "Download Canarias Conectada" block are both install cards, and both
     * are driven from here so the Android prompt and the iOS instructions are
     * decided once. A `querySelector` would light the first and leave the
     * other hidden forever.
     */
    revealCard(childSelector) {
        for (const card of document.querySelectorAll(".o_pwa_install_card")) {
            card.classList.remove("d-none");
            for (const child of card.querySelectorAll(childSelector)) {
                child.classList.remove("d-none");
            }
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
        this.hideCards();
    }

    hideCards() {
        for (const card of document.querySelectorAll(".o_pwa_install_card")) {
            card.classList.add("d-none");
        }
    }
}

registry.category("public.interactions").add("website_pwa.install", PWAInstall);
