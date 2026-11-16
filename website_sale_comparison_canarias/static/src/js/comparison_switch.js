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
 * is off, by narrowing the selector it is matched on: the layout puts
 * `data-wscc-comparison` on `<body>` only while the switch is on (the
 * `comparison_modal` template), and that is the switch as seen from the
 * browser. A selector, and not a patched `setup()`, because an interaction
 * that is never matched has no handlers bound and no state half-built. A
 * plain attribute selector on purpose: `:has()` would have made the WHOLE
 * selector invalid on any browser without it, and core's comparator would
 * then never work there even with the switch on.
 *
 * This module imports core's interaction, so it runs after it and before the
 * interaction service reads any selector; `querySelectorAll` matches the
 * `body[...]` ancestor even when the service searches from `#wrapwrap`.
 */
ProductComparison.selector =
    "body[data-wscc-comparison] .js_sale:not(.o_wsale_comparison_page)";
