/** @odoo-module **/
/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import comparisonUtils from "@website_sale_comparison/js/website_sale_comparison_utils";

/**
 * The compare button on a shop card: shows whether the product is already in
 * the comparison, and opens the picker.
 *
 * DELIBERATELY DECOUPLED from core's `.o_add_compare` hook. The button used
 * to carry both classes, so core's interaction owned the click too: it added
 * the product AND disabled the button (`comparisonUtils.updateDisabled`),
 * after which the picker could never be opened again from that product. This
 * button now only ever OPENS the modal — membership in the comparison is
 * decided by the checkboxes inside it — so it must never be disabled.
 *
 * Membership is read from the cookie through core's own utils (the list moved
 * from `localStorage` to the `comparison_product_ids` cookie once already;
 * going through the utils is what keeps this correct the next time it moves).
 * The modal announces every change with a `wscc:selection` event on the
 * document, which is what keeps these buttons honest while it is open.
 */
export class CompareButtons extends Interaction {
    static selector = "#wrapwrap";

    dynamicContent = {
        ".o_wscc_compare_btn": { "t-on-click": this.onCompareClick },
    };

    start() {
        this.paint();
        this.addListener(window, "pageshow", () => this.paint());
        this.addListener(document, "wscc:selection", () => this.paint());
    }

    paint() {
        const ids = new Set(comparisonUtils.getComparisonProductIds());
        for (const button of this.el.querySelectorAll(".o_wscc_compare_btn")) {
            const productId = parseInt(button.dataset.productProductId, 10);
            const on = ids.has(productId);
            button.classList.toggle("active", on);
            button.setAttribute("aria-pressed", on ? "true" : "false");
        }
    }

    onCompareClick(ev) {
        const button = ev.target.closest(".o_wscc_compare_btn");
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
        // opened nothing -- reported 2026-08-21 as "no funciona".
        if (window.Modal) {
            window.Modal.n(modal).show();
        }
    }
}

registry
    .category("public.interactions")
    .add("website_sale_comparison_canarias.compare_buttons", CompareButtons);
