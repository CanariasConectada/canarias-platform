/** @odoo-module **/
/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import { ProductComparison } from "@website_sale_comparison/interactions/product_comparison";

/**
 * Core's comparison interaction (the one that mounts the bottom bar and owns
 * every `.o_add_compare` click) behind the platform switch.
 *
 * With the comparator switched off (`website._wscc_comparison_enabled()`,
 * Website > Configuration > Settings > "Price comparator") the server renders
 * no compare control at all, but the bottom bar is not server-rendered: core
 * mounts it as an OWL component from this interaction, and it draws whatever
 * the `comparison_product_ids` cookie still holds. A visitor who compared
 * something before the switch was flipped would keep seeing the bar, with
 * its link to the comparison page, on every shop page.
 *
 * So the interaction is kept from being instantiated at all when the switch
 * is off, by narrowing the selector it is matched on: the layout renders the
 * picker (`#o_wscc_compare_modal`) only when the switch is on, and that is
 * the switch as seen from the browser. A selector, and not a patched
 * `setup()`, because an interaction that is never matched has no handlers
 * bound and no state half-built; and `:has()` rather than a class on
 * `#wrapwrap`, because the layout's wrapper attributes are core's to write
 * and this file loads after core's interaction (it imports it), before the
 * interaction service reads any selector.
 *
 * The AJAX shop grid, the product page and the classic listing all carry
 * `.js_sale` on `#wrap`, a sibling of the picker under `#wrapwrap`, hence
 * the `body:has()` ancestor form.
 */
ProductComparison.selector = "body:has(#o_wscc_compare_modal) .js_sale:not(.o_wsale_comparison_page)";
