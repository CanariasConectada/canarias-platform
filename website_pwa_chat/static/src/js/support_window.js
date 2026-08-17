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
            // Without JavaScript this listener never runs and the <a href>
            // does what it always did: navigate to the full page.
            event.preventDefault();
            this.toggle();
        });
        this.addListener(this.closeEl, "click", () => this.close());
        this.addListener(this.el.ownerDocument, "keydown", (event) => {
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
