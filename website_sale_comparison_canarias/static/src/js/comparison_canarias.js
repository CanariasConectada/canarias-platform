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
 * Previously this read the list from `localStorage["comparelist_product_ids"]`
 * -- a key Odoo has not written since the comparison moved to the
 * `comparison_product_ids` COOKIE. Nothing crashed; the button simply never
 * lit up. Reading through core's own utils is what stops that from happening
 * again the next time core changes where it keeps the list.
 *
 * Core's own interaction still owns the click: it adds the product to the
 * comparison. This adds the picker on top, so one click both starts the
 * comparison and offers what to compare against.
 */
export class CompareButtons extends Interaction {
    static selector = "#wrapwrap";

    dynamicContent = {
        ".o_wscc_compare_btn": { "t-on-click": this.onCompareClick },
    };

    start() {
        this.paint();
        // Core writes the cookie on its own click handler, which may run after
        // ours; repainting on the next tick is enough to read the settled
        // value without racing it.
        this.addListener(window, "pageshow", () => this.paint());
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
        // page where the shop assets are not loaded.
        const Modal = window.bootstrap && window.bootstrap.Modal;
        if (Modal) {
            Modal.getOrCreateInstance(modal).show();
        }
        this.waitForTimeout(() => this.paint(), 100);
    }
}

registry
    .category("public.interactions")
    .add("website_sale_comparison_canarias.compare_buttons", CompareButtons);
