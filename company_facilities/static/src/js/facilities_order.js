/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {registry} from "@web/core/registry";
import {Interaction} from "@web/public/interaction";

/**
 * Put the facilities block ABOVE the funding-logos band.
 *
 * The two blocks cannot be ordered server side: the band is page content --
 * the section named "Subvenciones", present on all 218 migrated homepages --
 * rendered inside #wrap, while this block is layout, injected before the
 * footer as #wrap's sibling. No template inherits across that boundary, so
 * the swap is done here, in the one place that can see both.
 *
 * Moving OUR block to the band, never the reverse: the band is the shops'
 * own authored content and stays exactly where its author put it whenever
 * this block is absent (facilities disabled, or nothing ticked).
 */
export class FacilitiesAboveGrants extends Interaction {
    static selector = "section.o_cf_facilities";

    start() {
        const band = this.el.ownerDocument.querySelector(
            '#wrap section[data-name="Subvenciones"]'
        );
        if (band) {
            band.before(this.el);
        }
    }
}

registry
    .category("public.interactions")
    .add("company_facilities.facilities_above_grants", FacilitiesAboveGrants);
