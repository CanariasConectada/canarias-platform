/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {registry} from "@web/core/registry";
import {Interaction} from "@web/public/interaction";

/**
 * The floating support window.
 *
 * All this file does is show and hide a box and, ONCE, promote the iframe's
 * data-src to src. Everything that happens inside the box is the ordinary
 * /chat/soporte page: no message logic, no bus subscription, no state lives
 * here. That is the deal that keeps the window and the full page from ever
 * disagreeing.
 *
 * The lazy src is load-bearing, not a nicety: /chat/soporte creates a guest
 * and a conversation for whoever requests it, and this template is on every
 * page of all 218 sites. An iframe that loaded eagerly would open one empty
 * support conversation per page view platform-wide.
 */
export class SupportWindow extends Interaction {
    static selector = ".o_cc_chat_fab_zone";

    setup() {
        this.fabEl = this.el.querySelector(".o_cc_chat_fab");
        this.windowEl = this.el.querySelector(".o_cc_chat_window");
        this.frameEl = this.el.querySelector(".o_cc_chat_window_frame");
        this.closeEl = this.el.querySelector(".o_cc_chat_window_close");
    }

    start() {
        if (!this.fabEl || !this.windowEl || !this.frameEl) {
            return;
        }
        this.addListener(this.fabEl, "click", (event) => {
            // The fab carries its URL in data-href, so an unbound button
            // navigates nowhere; the <noscript> twin in the template keeps
            // the real link for the no-JavaScript visitor.
            event.preventDefault();
            this.toggle();
        });
        // role="button" promises keyboard activation, and a data-href anchor
        // no longer gets it for free from the browser.
        this.addListener(this.fabEl, "keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                this.toggle();
            }
        });
        this.addListener(this.closeEl, "click", () => this.close());
        this.addListener(this.el.ownerDocument, "keydown", (event) => {
            if (event.key === "Escape" && this.isOpen()) {
                this.close();
            }
        });
        // Escape must work once focus is INSIDE the frame too: keydown fires
        // in the iframe's own document, which the page's listener never sees.
        // Bound after every load because each load is a new document. The
        // zone portals frame the host site cross-subdomain, where
        // contentDocument is null -- there the page's own Escape handler
        // still covers the pre-focus case, and the close button the rest.
        this.addListener(this.frameEl, "load", () => this.bindFrameEscape());
        // The stylesheet hides the fab under the open mobile menu with
        // :has(.show), but Bootstrap spends 0.3s in .showing first and some
        // browsers have no :has() at all -- there the fab floats over the
        // offcanvas and steals its last tap. These events bubble to the
        // document in every browser, so hiding never depends on :has().
        this.addListener(this.el.ownerDocument, "show.bs.offcanvas", () => {
            this.el.classList.add("o_cc_chat_fab_zone_hidden");
        });
        this.addListener(this.el.ownerDocument, "hidden.bs.offcanvas", () => {
            this.el.classList.remove("o_cc_chat_fab_zone_hidden");
        });
    }

    bindFrameEscape() {
        let frameDoc = null;
        try {
            frameDoc = this.frameEl.contentDocument;
        } catch {
            frameDoc = null;
        }
        if (!frameDoc) {
            return;
        }
        this.addListener(frameDoc, "keydown", (event) => {
            if (event.key === "Escape" && this.isOpen()) {
                this.close();
            }
        });
    }

    isOpen() {
        return !this.windowEl.classList.contains("d-none");
    }

    toggle() {
        if (this.isOpen()) {
            this.close();
        } else {
            this.open();
        }
    }

    open() {
        if (!this.frameEl.getAttribute("src")) {
            this.frameEl.setAttribute("src", this.frameEl.dataset.src);
        }
        this.windowEl.classList.remove("d-none");
        this.fabEl.setAttribute("aria-expanded", "true");
        // The frame is another document, so focus lands on its body: enough
        // for a keyboard user to Tab straight into the conversation.
        this.frameEl.focus();
    }

    close() {
        this.windowEl.classList.add("d-none");
        this.fabEl.setAttribute("aria-expanded", "false");
        // Hand focus back to the button that opened it, so closing with
        // Escape does not drop a keyboard user at the top of the page.
        this.fabEl.focus();
    }
}

registry
    .category("public.interactions")
    .add("website_pwa_chat.support_window", SupportWindow);
