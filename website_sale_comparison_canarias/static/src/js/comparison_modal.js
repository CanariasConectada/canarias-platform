/** @odoo-module **/
/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import comparisonUtils from "@website_sale_comparison/js/website_sale_comparison_utils";

/**
 * Pick what to compare against, without leaving the shop.
 *
 * Core's flow is "add products one by one, then go to /shop/compare", which
 * asks the visitor to remember what they saw three pages ago. This opens a
 * picker instead, already narrowed to the categories of the product they
 * clicked, and hands the result straight to core's comparison table.
 *
 * The compare list itself stays core's: the cookie, the four-product cap and
 * the change event all come from its utils, so the drawer, the table and this
 * modal can never disagree about what is being compared.
 */
export class ComparisonModal extends Interaction {
    static selector = ".o_wscc_compare_modal";

    setup() {
        this.state = {
            products: [],
            categories: [],
            activeCategoryIds: [],
            loading: false,
        };
        this.listEl = this.el.querySelector(".o_wscc_modal_list");
        this.chipsEl = this.el.querySelector(".o_wscc_modal_chips");
        this.countEl = this.el.querySelector(".o_wscc_modal_count");
        this.emptyEl = this.el.querySelector(".o_wscc_modal_empty");
    }

    start() {
        this.el.addEventListener("wscc:open", (ev) => this.open(ev.detail.templateId));
        this.el.addEventListener("click", (ev) => this.onClick(ev));
    }

    async open(templateId) {
        this.setLoading(true);
        try {
            const data = await this.waitFor(
                rpc("/shop/compare/candidates", {
                    product_template_id: templateId,
                })
            );
            this.state.products = data.products || [];
            this.state.categories = data.categories || [];
            // Open on "things like this one", which is the whole point of the
            // modal. Only keep the ones that actually have candidates, so the
            // preselection can never produce an empty list on open.
            const available = new Set(this.state.categories.map((c) => c.id));
            this.state.activeCategoryIds = (data.current_category_ids || []).filter(
                (id) => available.has(id)
            );
            this.render();
        } finally {
            this.setLoading(false);
        }
    }

    setLoading(loading) {
        this.state.loading = loading;
        this.el.classList.toggle("o_wscc_loading", loading);
    }

    visibleProducts() {
        const active = this.state.activeCategoryIds;
        if (!active.length) {
            return this.state.products;
        }
        return this.state.products.filter((product) =>
            product.category_ids.some((id) => active.includes(id))
        );
    }

    render() {
        const compared = new Set(comparisonUtils.getComparisonProductIds());
        const products = this.visibleProducts();

        this.chipsEl.replaceChildren(
            ...this.state.categories.map((category) => {
                const chip = document.createElement("button");
                chip.type = "button";
                chip.className = "btn btn-sm o_wscc_modal_chip";
                chip.classList.toggle(
                    "active",
                    this.state.activeCategoryIds.includes(category.id)
                );
                chip.dataset.categoryId = category.id;
                chip.textContent = category.name;
                return chip;
            })
        );

        this.listEl.replaceChildren(
            ...products.map((product) => this.renderProduct(product, compared))
        );
        this.emptyEl.classList.toggle("d-none", products.length > 0);
        this.countEl.textContent = compared.size;
    }

    renderProduct(product, compared) {
        const row = document.createElement("label");
        row.className = "o_wscc_modal_item";

        const input = document.createElement("input");
        input.type = "checkbox";
        input.className = "form-check-input me-2";
        input.dataset.variantId = product.variant_id;
        input.checked = compared.has(product.variant_id);
        // Core caps the comparison at four; disabling the rest says so before
        // the click instead of after it.
        input.disabled =
            !input.checked &&
            compared.size >= comparisonUtils.MAX_COMPARISON_PRODUCTS;

        const image = document.createElement("img");
        image.className = "o_wscc_modal_img";
        image.src = product.image_url;
        image.alt = "";
        image.loading = "lazy";

        const name = document.createElement("span");
        name.className = "o_wscc_modal_name";
        name.textContent = product.name;

        const price = document.createElement("span");
        price.className = "o_wscc_modal_price ms-auto";
        price.textContent = product.price;

        row.append(input, image, name, price);
        return row;
    }

    onClick(ev) {
        const chip = ev.target.closest(".o_wscc_modal_chip");
        if (chip) {
            const id = parseInt(chip.dataset.categoryId, 10);
            const active = this.state.activeCategoryIds;
            const at = active.indexOf(id);
            if (at === -1) {
                active.push(id);
            } else {
                active.splice(at, 1);
            }
            this.render();
            return;
        }

        const checkbox = ev.target.closest("input[data-variant-id]");
        if (checkbox) {
            const variantId = parseInt(checkbox.dataset.variantId, 10);
            // No bus on purpose. Core's bottom bar listens on an EventBus its
            // own interaction creates privately (`this.bus = new EventBus()`),
            // which nothing outside that instance can reach; the util already
            // guards with `if (bus)`. The cookie is the shared state that
            // matters, and the modal's own button leaves for /shop/compare,
            // which rebuilds everything from it.
            if (checkbox.checked) {
                comparisonUtils.addComparisonProduct(variantId);
            } else {
                comparisonUtils.removeComparisonProduct(variantId);
            }
            this.render();
        }
    }
}

registry
    .category("public.interactions")
    .add("website_sale_comparison_canarias.comparison_modal", ComparisonModal);
