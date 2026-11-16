/** @odoo-module **/
/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import comparisonUtils from "@website_sale_comparison/js/website_sale_comparison_utils";

// How long a pause in typing means "done typing". Short enough to feel live,
// long enough not to fire a request per keystroke.
const SEARCH_DEBOUNCE_MS = 300;

// Below this the usage help opens folded: four lines of help on a phone would
// push the product list, which is the point of the modal, off the screen.
const HELP_OPEN_MEDIA = "(min-width: 768px)";

// Several chips clicked in a row are one question, not several: the chips
// repaint at once and the list is asked for when the clicking pauses.
const CHIP_DEBOUNCE_MS = 200;

/**
 * Pick what to compare against, without leaving the shop.
 *
 * Core's flow is "add products one by one, then go to /shop/compare", which
 * asks the visitor to remember what they saw three pages ago. This opens a
 * picker instead, already narrowed to the categories of the product they
 * clicked, and hands the result straight to core's comparison table.
 *
 * Four numbered steps, in the order the help at the top explains them: the
 * scope, the product's own category (ticked on open, can only be unticked),
 * the other categories (folded, none picked) and the products. The server
 * applies all three filters; this only says what is ticked and draws what
 * comes back, because the candidate pool is capped and a client-side filter
 * would only ever see its first alphabetical page.
 *
 * The compare list itself stays core's: the cookie, the four-product cap and
 * the change event all come from its utils, so the drawer, the table and this
 * modal can never disagree about what is being compared.
 */
export class ComparisonModal extends Interaction {
    static selector = ".o_wscc_compare_modal";

    setup() {
        this.state = {
            templateId: null,
            products: [],
            // Step 2: the clicked product's own categories, and which of
            // them are still ticked. `null` asks the server for its default
            // (all of them), which is how the modal opens.
            sameCategories: [],
            sameCategoryIds: null,
            // Step 3: every other category on offer, and the picked ones.
            categories: [],
            activeCategoryIds: [],
            // The four scopes, as the server says they apply here.
            scopes: [],
            scope: null,
            zone: "",
            query: "",
            // How many candidates the scope holds server-side; more than
            // `products.length` means the pool was truncated at the cap.
            total: 0,
            loading: false,
        };
        // Only the latest request may paint: every chip is a round trip now,
        // and two quick clicks can answer out of order.
        this.loadTicket = 0;
        this.listEl = this.el.querySelector(".o_wscc_modal_list");
        this.chipsEl = this.el.querySelector(".o_wscc_modal_chips");
        this.helpEl = this.el.querySelector(".o_wscc_modal_help");
        this.sameStepEl = this.el.querySelector(".o_wscc_modal_step_same");
        this.sameChipsEl = this.el.querySelector(".o_wscc_modal_same_chips");
        this.otherEl = this.el.querySelector(".o_wscc_modal_other");
        this.otherCountEl = this.el.querySelector(".o_wscc_modal_other_count");
        this.otherNoneEl = this.el.querySelector(".o_wscc_modal_other_none");
        this.errorEl = this.el.querySelector(".o_wscc_modal_error");
        // `debounced` cancels itself on destroy, like the search below.
        this.loadAfterChips = this.debounced(
            () => this.load({ keepCategories: true }),
            CHIP_DEBOUNCE_MS
        );
        this.countEl = this.el.querySelector(".o_wscc_modal_count");
        this.emptyEl = this.el.querySelector(".o_wscc_modal_empty");
        this.scopesEl = this.el.querySelector(".o_wscc_modal_scopes");
        this.zonesEl = this.el.querySelector(".o_wscc_modal_zones");
        this.zoneSelectEl = this.el.querySelector("#o_wscc_zone_select");
        this.searchEl = this.el.querySelector(".o_wscc_modal_search_input");
        this.truncatedEl = this.el.querySelector(".o_wscc_modal_truncated");
        this.shownEl = this.el.querySelector(".o_wscc_modal_shown");
        this.totalEl = this.el.querySelector(".o_wscc_modal_total");
        this.goEl = this.el.querySelector(".o_wscc_modal_go");
    }

    start() {
        this.el.addEventListener("wscc:open", (ev) => this.open(ev.detail.templateId));
        this.el.addEventListener("click", (ev) => this.onClick(ev));
        this.el.addEventListener("change", (ev) => this.onChange(ev));
        if (this.searchEl) {
            // `debounced` cancels itself on destroy, so a half-typed query
            // can never fire against a dead interaction.
            this.addListener(
                this.searchEl,
                "input",
                this.debounced(() => this.applySearch(), SEARCH_DEBOUNCE_MS)
            );
        }
    }

    async open(templateId) {
        this.state.templateId = templateId;
        // A fresh product is a fresh question: the scope the visitor picked
        // for a jacket says nothing about the one they want for a drill, and
        // neither does the name they typed.
        this.state.scope = null;
        this.state.zone = "";
        this.state.query = "";
        if (this.searchEl) {
            this.searchEl.value = "";
        }
        // Folded again for every product: the other categories are the
        // exception, not the way in.
        if (this.otherEl) {
            this.otherEl.open = false;
        }
        if (this.helpEl) {
            this.helpEl.open = window.matchMedia(HELP_OPEN_MEDIA).matches;
        }
        await this.load({ keepCategories: false });
    }

    /**
     * Ask the server for the candidates of the current scope.
     *
     * Changing the scope goes back to the server rather than filtering what
     * is already loaded, and it has to: "toda Canarias Conectada" is a
     * different catalogue, not a wider view of this one, and the price shown
     * has to be the price of the shop being compared against. The search
     * query goes back too, because the candidate pool is capped server-side
     * and a client filter could never reach past the cap. The categories go
     * back for the same reason.
     *
     * `keepCategories: false` asks for the default again -- the product's own
     * category ticked, no other one picked.
     */
    async load({ keepCategories }) {
        const ticket = ++this.loadTicket;
        this.setLoading(true);
        try {
            const data = await this.waitFor(
                rpc("/shop/compare/candidates", {
                    product_template_id: this.state.templateId,
                    scope: this.state.scope,
                    zone: this.state.zone,
                    query: this.state.query,
                    same_category_ids: keepCategories
                        ? this.state.sameCategoryIds
                        : null,
                    category_ids: keepCategories ? this.state.activeCategoryIds : [],
                })
            );
            if (ticket !== this.loadTicket) {
                return;
            }
            this.setError(false);
            this.state.products = data.products || [];
            this.state.sameCategories = data.same_categories || [];
            this.state.categories = data.categories || [];
            this.state.scopes = data.scopes || [];
            this.state.total = data.total || 0;
            // The server has the last word on the scope: it falls back when
            // the one asked for is not available here.
            this.state.scope = data.scope || null;
            this.state.zone = data.zone || "";
            // ... and on the categories: it answers with what it actually
            // applied, which is the product's real categories and the chips
            // this scope really offers, whatever was asked for.
            this.state.sameCategoryIds = data.same_category_ids || [];
            this.state.activeCategoryIds = data.selected_category_ids || [];
            this.render();
        } catch (error) {
            // A dead network or a 500 must not look like "nothing to
            // compare". Say so where the list would be, and leave the scopes
            // and the chips as they are: the next click simply asks again.
            // (`waitFor` passes a rejection on even after destroy, when
            // nobody is left to tell.)
            if (ticket === this.loadTicket && !this.isDestroyed) {
                console.warn("Could not load the comparison candidates", error);
                this.state.products = [];
                this.state.total = 0;
                this.render();
                this.setError(true);
            }
        } finally {
            if (ticket === this.loadTicket) {
                this.setLoading(false);
            }
        }
    }

    setError(failed) {
        if (this.errorEl) {
            this.errorEl.classList.toggle("d-none", !failed);
        }
        if (failed) {
            // One message at a time: "could not load" already explains the
            // empty list.
            this.emptyEl.classList.add("d-none");
        }
    }

    setLoading(loading) {
        this.state.loading = loading;
        this.el.classList.toggle("o_wscc_loading", loading);
    }

    /**
     * A category chip: a toggle button that says so to assistive technology
     * (`aria-pressed`) and not only through its colour.
     */
    renderChip(category, pressed, className) {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = `btn btn-sm o_wscc_modal_chip ${className}`;
        chip.classList.toggle("active", pressed);
        chip.setAttribute("aria-pressed", pressed ? "true" : "false");
        chip.dataset.categoryId = category.id;
        if (pressed) {
            const tick = document.createElement("span");
            tick.className = "fa fa-check me-1";
            tick.setAttribute("role", "presentation");
            chip.append(tick);
        }
        chip.append(category.name);
        return chip;
    }

    /**
     * Steps 2 and 3. A product with no category has no step 2: the section
     * and its line of help go away together, and the numbering (a CSS counter
     * on the titles, the <ol> in the help) closes the gap by itself.
     */
    renderCategories() {
        // The chips are rebuilt, so the one that was just toggled from the
        // keyboard would lose the focus with it; hand it back below.
        const focused = this.el.contains(document.activeElement)
            ? document.activeElement.closest(".o_wscc_modal_chip")
            : null;
        const focusedId = focused && focused.dataset.categoryId;
        const same = this.state.sameCategories;
        const hasSame = same.length > 0;
        this.sameStepEl.classList.toggle("d-none", !hasSame);
        for (const el of this.el.querySelectorAll(".o_wscc_modal_help_same")) {
            el.classList.toggle("d-none", !hasSame);
        }
        for (const el of this.el.querySelectorAll(".o_wscc_modal_help_title_4")) {
            el.classList.toggle("d-none", !hasSame);
        }
        for (const el of this.el.querySelectorAll(".o_wscc_modal_help_title_3")) {
            el.classList.toggle("d-none", hasSame);
        }
        const ticked = this.state.sameCategoryIds || [];
        this.sameChipsEl.replaceChildren(
            ...same.map((category) =>
                this.renderChip(
                    category,
                    ticked.includes(category.id),
                    "o_wscc_modal_chip_same"
                )
            )
        );

        const others = this.state.categories;
        const active = this.state.activeCategoryIds;
        this.otherEl.classList.toggle("d-none", others.length === 0);
        this.otherNoneEl.classList.toggle("d-none", others.length > 0);
        // Null-checked: the count lives inside a translatable sentence, and a
        // translation that drops the <span> must cost the number, not the
        // whole modal.
        if (this.otherCountEl) {
            this.otherCountEl.textContent = others.length;
        }
        // A picked category must stay in sight. Never folded from here: that
        // is the visitor's call.
        if (active.length) {
            this.otherEl.open = true;
        }
        this.chipsEl.replaceChildren(
            ...others.map((category) =>
                this.renderChip(
                    category,
                    active.includes(category.id),
                    "o_wscc_modal_chip_other"
                )
            )
        );
        if (focusedId) {
            const again = this.el.querySelector(
                `.o_wscc_modal_chip[data-category-id="${focusedId}"]`
            );
            if (again) {
                again.focus();
            }
        }
    }

    renderScopes() {
        this.scopesEl.replaceChildren(
            ...this.state.scopes.map((scope) => {
                const button = document.createElement("button");
                button.type = "button";
                const active = scope.key === this.state.scope;
                button.className =
                    "btn btn-sm o_wscc_modal_scope " +
                    (active ? "btn-primary" : "btn-outline-secondary");
                button.dataset.scope = scope.key;
                button.setAttribute("aria-pressed", active ? "true" : "false");
                button.textContent = scope.label;
                return button;
            })
        );

        const current = this.state.scopes.find((s) => s.key === this.state.scope);
        const zones = (current && current.zones) || [];
        this.zonesEl.classList.toggle("d-none", zones.length === 0);
        if (zones.length) {
            // "Outside my zone" answers with one click (zone "") and the
            // named zones stay available as an optional refinement.
            const allOption = document.createElement("option");
            allOption.value = "";
            allOption.textContent = _t("All other zones");
            allOption.selected = !this.state.zone;
            this.zoneSelectEl.replaceChildren(
                allOption,
                ...zones.map((zone) => {
                    const option = document.createElement("option");
                    option.value = zone.key;
                    option.textContent = zone.name;
                    option.selected = zone.key === this.state.zone;
                    return option;
                })
            );
        }
    }

    render() {
        const comparisonIds = comparisonUtils.getComparisonProductIds();
        const compared = new Set(comparisonIds);
        // Already filtered by scope, categories and query, server-side.
        const products = this.state.products;

        this.renderScopes();
        this.renderCategories();

        this.listEl.replaceChildren(
            ...products.map((product) => this.renderProduct(product, compared))
        );
        this.emptyEl.classList.toggle("d-none", products.length > 0);

        // "Showing 120 of N": N is what the scope and the ticked categories
        // hold server-side; anything past the cap is only reachable by
        // searching (or by narrowing the categories).
        const truncated = this.state.total > this.state.products.length;
        this.truncatedEl.classList.toggle("d-none", !truncated);
        if (truncated) {
            this.shownEl.textContent = this.state.products.length;
            this.totalEl.textContent = this.state.total;
        }

        this.countEl.textContent = compared.size;
        this.renderCallToAction(comparisonIds);
    }

    /**
     * The footer CTA: disabled until there are at least two products to
     * compare, and pointing at the comparison of exactly the ticked ones —
     * the same URL core's bottom bar builds from the cookie.
     */
    renderCallToAction(comparisonIds) {
        if (!this.goEl) {
            return;
        }
        const enabled = comparisonIds.length >= 2;
        this.goEl.classList.toggle("disabled", !enabled);
        this.goEl.setAttribute("aria-disabled", enabled ? "false" : "true");
        this.goEl.tabIndex = enabled ? 0 : -1;
        this.goEl.setAttribute(
            "href",
            enabled
                ? `/shop/compare?products=${encodeURIComponent(comparisonIds.join(","))}`
                : "#"
        );
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

        // The name links to the product page so a candidate can be inspected
        // before being compared. A new tab, because closing the modal to look
        // at one candidate would throw away the whole selection in progress.
        // (Clicking a nested link does not toggle the wrapping label: label
        // activation skips interactive targets.)
        const name = document.createElement("a");
        name.className = "o_wscc_modal_name";
        name.href = product.url;
        name.target = "_blank";
        name.rel = "noopener";
        name.textContent = product.name;

        const price = document.createElement("span");
        price.className = "o_wscc_modal_price ms-auto";
        price.textContent = product.price;

        row.append(input, image, name, price);
        return row;
    }

    applySearch() {
        const query = this.searchEl.value.trim();
        if (query === this.state.query) {
            return;
        }
        this.state.query = query;
        this.load({ keepCategories: true });
    }

    onChange(ev) {
        const select = ev.target.closest("#o_wscc_zone_select");
        if (select) {
            this.state.zone = select.value;
            // Categories are not carried over: another neighbourhood has its
            // own catalogue and the old selection would often filter it to
            // nothing.
            this.load({ keepCategories: false });
        }
    }

    onClick(ev) {
        const scopeButton = ev.target.closest(".o_wscc_modal_scope");
        if (scopeButton) {
            const scope = scopeButton.dataset.scope;
            if (scope === this.state.scope) {
                return;
            }
            this.state.scope = scope;
            // "Outside my zone" opens on everything outside it (zone "");
            // a named zone is one select away.
            this.state.zone = "";
            this.load({ keepCategories: true });
            return;
        }

        const chip = ev.target.closest(".o_wscc_modal_chip");
        if (chip) {
            const id = parseInt(chip.dataset.categoryId, 10);
            const same = chip.classList.contains("o_wscc_modal_chip_same");
            const key = same ? "sameCategoryIds" : "activeCategoryIds";
            const ids = this.state[key] || [];
            // A new array, never a splice: `null` and the server's own list
            // both have to survive being toggled.
            this.state[key] = ids.includes(id)
                ? ids.filter((other) => other !== id)
                : [...ids, id];
            // Paint the chip at once; the list follows when the clicking
            // pauses and the server answers.
            this.renderCategories();
            this.loadAfterChips();
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
            // Tell the compare buttons on the page behind the modal, which
            // paint themselves from the same cookie.
            document.dispatchEvent(new CustomEvent("wscc:selection"));
        }
    }
}

registry
    .category("public.interactions")
    .add("website_sale_comparison_canarias.comparison_modal", ComparisonModal);
