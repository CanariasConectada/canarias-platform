/* Copyright 2026 Canarias Conectada
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {onWillUnmount} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {useBus} from "@web/core/utils/hooks";
import {debounce} from "@web/core/utils/timing";
import {getFieldDomain} from "@web/model/relational_model/utils";
import {
    Many2ManyCheckboxesField,
    many2ManyCheckboxesField,
} from "@web/views/fields/many2many_checkboxes/many2many_checkboxes_field";
import {useSpecialData} from "@web/views/fields/relational_utils";

/**
 * The catalogue as checkboxes under their subdivision headings.
 *
 * ``many2many_checkboxes`` lists the comodel flat, in ``_order`` but with no
 * sign of the subdivision, which is what the client read as "no order at all"
 * (2026-09-15). A static list cannot be grouped in Odoo 19 either, so the
 * grouping is done here: one fetch that also carries ``category_id``, then
 * one heading per subdivision, in the order the catalogue defines.
 *
 * Everything about ticking -- batching the changes, committing them on
 * unmount -- is the parent's, untouched. Only the fetch and the template
 * differ, and the fetch is the reason ``super.setup()`` is not called: the
 * parent's own fetch is a ``name_search`` that has no room for the category.
 */
export class FacilityCheckboxesField extends Many2ManyCheckboxesField {
    static template = "company_facilities.FacilityCheckboxesField";

    setup() {
        this.specialData = useSpecialData((orm, props) => {
            const {relation} = props.record.fields[props.name];
            const domain = getFieldDomain(props.record, props.name, props.domain);
            return orm
                .call(relation, "web_search_read", [], {
                    domain,
                    specification: {
                        display_name: {},
                        category_id: {fields: {display_name: {}}},
                    },
                    context: this.props.context || {},
                })
                .then((result) => result.records);
        });
        this.idsToAdd = new Set();
        this.idsToRemove = new Set();
        this.debouncedCommitChanges = debounce(this.commitChanges.bind(this), 500);
        useBus(this.props.record.model.bus, "NEED_LOCAL_CHANGES", this.commitChanges.bind(this));
        onWillUnmount(this.commitChanges.bind(this));
    }

    /**
     * ``[{id, name, items: [[id, name], ...]}, ...]`` in catalogue order.
     *
     * Items keep the parent's ``[id, name]`` shape so ``isSelected`` and
     * ``onChange`` are inherited as they are.
     */
    get groups() {
        const groups = [];
        const byCategory = new Map();
        for (const record of this.specialData.data || []) {
            const category = record.category_id || {id: 0, display_name: ""};
            let group = byCategory.get(category.id);
            if (!group) {
                group = {id: category.id, name: category.display_name, items: []};
                byCategory.set(category.id, group);
                groups.push(group);
            }
            group.items.push([record.id, record.display_name]);
        }
        return groups;
    }
}

export const facilityCheckboxesField = {
    ...many2ManyCheckboxesField,
    component: FacilityCheckboxesField,
    displayName: _t("Checkboxes by subdivision"),
};

registry.category("fields").add("facility_checkboxes", facilityCheckboxesField);
