/** @odoo-module **/
/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import comparisonUtils from "@website_sale_comparison/js/website_sale_comparison_utils";

/**
 * The compare button on the product page: opens the scoped picker (which
 * shop, which category) to choose what to compare against.
 *
 * ONLY the product page button (`.o_wscc_compare_btn_picker`) goes through
 * this class. The shop-grid cards carry core's own `.o_add_compare` instead
 * (2026-08-21): the visitor asked to keep the grid on core's stock
 * one-by-one flow — click a card, it joins the comparison, the bottom bar
 * picks it up — and reserve "compare against what" for the product page,
 * where that question actually needs asking. Before this button ALSO
 * carried `.o_add_compare`, the two interactions raced: core added the
 * product AND disabled the button, after which the picker could never be
 * opened again from that product. It is scoped to the picker class alone
 * now, so it can stay permanently clickable without that conflict.
 *
 * Membership is read from the cookie through core's own utils (the list moved
 * from `localStorage` to the `comparison_product_ids` cookie once already;
 * going through the utils is what keeps this correct the next time it moves).
 * The modal announces every change with a `wscc:selection` event on the
 * document, which is what keeps this button's own "already in the
 * comparison" state honest while it is open.
 */
export class CompareButtons extends Interaction {
    static selector = "#wrapwrap";

    dynamicContent = {
        ".o_wscc_compare_btn_picker": { "t-on-click": this.onCompareClick },
    };

    start() {
        this.paint();
        this.addListener(window, "pageshow", () => this.paint());
        this.addListener(document, "wscc:selection", () => this.paint());
    }

    paint() {
        const ids = new Set(comparisonUtils.getComparisonProductIds());
        for (const button of this.el.querySelectorAll(".o_wscc_compare_btn_picker")) {
            const productId = parseInt(button.dataset.productProductId, 10);
            const on = ids.has(productId);
            button.classList.toggle("active", on);
            button.setAttribute("aria-pressed", on ? "true" : "false");
        }
    }

    onCompareClick(ev) {
        const button = ev.target.closest(".o_wscc_compare_btn_picker");
        const modal = document.querySelector(".o_wscc_compare_modal");
        if (!button || !modal) {
            return;
        }
        modal.dispatchEvent(
            new CustomEvent("wscc:open", {
                detail: { templateId: parseInt(button.dataset.productTemplateId, 10) },
            })
        );
        // Bootstrap is what renders the dialog; asking for it through the
        // global keeps this file free of a hard import that would fail on any
        // page where the shop assets are not loaded. Odoo 19's frontend does
        // NOT expose `window.bootstrap` (that was the old jQuery-era global);
        // its own trimmed bundle exposes each component directly on `window`
        // instead (`window.Modal`, `window.Popover`, ...), the same way core
        // itself opens dialogs (e.g. website_event's registration modal). The
        // old `window.bootstrap.Modal` check always failed, so the button
        // opened nothing -- reported 2026-08-21 as "no funciona". First fix
        // tried `window.Modal.n(...)`, copied from a grep hit in core's own
        // source tree -- but `.n` only exists on the pre-built/minified
        // bundle those files ship as; the plain global class exposes the
        // real, unminified static method inherited from BaseComponent.
        if (window.Modal) {
            window.Modal.getOrCreateInstance(modal).show();
        }
    }
}

registry
    .category("public.interactions")
    .add("website_sale_comparison_canarias.compare_buttons", CompareButtons);
