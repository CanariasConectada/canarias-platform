# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo import models
from odoo.fields import Domain


def _wsc_merge_key(name):
    """The identity under which same-named categories merge.

    Each merchant creates their own "Accesorios" category, so the aggregated
    shop would otherwise offer the same label five or six times. Categories
    merge when their names match after trimming, collapsing inner whitespace
    and case-folding — nothing smarter, because a visitor reading two options
    spelled identically cannot tell them apart either.
    """
    return " ".join((name or "").split()).casefold()


class Website(models.Model):
    _inherit = "website"

    def _wsc_zone_label(self):
        """Human label of this website's marketplace zone, or False.

        The selection lives on ``marketplace_zone`` (website_sale_marketplace)
        and is only populated when res_company_zone is installed; an empty
        selection or no zone both answer False, so the hero template can fall
        back to the portal wording without special cases.
        """
        self.ensure_one()
        if not self.marketplace_zone:
            return False
        selection = self._fields["marketplace_zone"]._description_selection(self.env)
        return dict(selection).get(self.marketplace_zone) or False

    def _wsc_shop_domain(self):
        """What this website's shop really lists, published-only.

        ``sale_product_domain()`` is the platform's single source of truth for
        the shop's product set — website_sale_marketplace already reshapes it
        for the portal and the zone shops. The explicit ``is_published`` leaf
        is NOT redundant: the callers search as sudo (a visitor cannot read
        other merchants' companies), and sudo bypasses the record rule that
        would otherwise hide unpublished products.
        """
        self.ensure_one()
        return Domain(self.sale_product_domain()) & Domain("is_published", "=", True)

    def _wsc_shop_categories(self):
        """Public categories of the products this website's shop lists.

        Computed from the shop domain rather than from all categories so a
        zone shop only offers the categories of its own neighbourhood — the
        same behaviour the legacy shop implemented per website type by hand.

        Read as the CURRENT user, not sudo: the shop is a public page and the
        ``website_published`` record rule is what keeps one merchant's
        microsite from listing another's categories. sudo would drop that
        second line of defence and lean the whole isolation on the domain
        being exactly right — which is precisely the mistake to avoid on the
        page a visitor reaches.
        """
        self.ensure_one()
        products = self.env["product.template"].search(self._wsc_shop_domain())
        categories = products.public_categ_ids
        return categories.sorted(lambda category: (category.name or "").lower())

    def _wsc_shop_category_tree(self):
        """The shop's categories in two levels, merged by name, nothing pruned.

        Same category SET as ``_wsc_shop_categories`` — this only changes the
        shape. Each category hangs under its topmost ancestor that is itself
        part of the set; a category whose ancestors sell nothing here becomes
        a top level of its own. Deeper chains are flattened to the second
        level, so every category the flat sidebar listed is still offered:
        either as a main category or as a subcategory of one.

        Categories spelling the same name (see ``_wsc_merge_key``) collapse
        into ONE option per level: every merchant creates their own
        "Accesorios", and the aggregated shop must offer one "Accesorios"
        that means all of them. Each node therefore carries the whole
        recordset it stands for, plus a stable representative ``id`` (the
        lowest) that the URL and the ``<option>`` values use.

        Returns a list of ``{"id": int, "name": str, "categories": recordset,
        "children": [same-shaped dicts]}`` nodes, both levels sorted
        alphabetically like the flat list was.
        """
        self.ensure_one()
        categories = self._wsc_shop_categories()
        listed_ids = set(categories.ids)

        def topmost_listed_ancestor(category):
            top = category
            node = category
            while node.parent_id:
                node = node.parent_id
                if node.id in listed_ids:
                    top = node
            return top

        def merged_entry(records):
            # Sorted so the representative id — what the URL carries — does
            # not depend on which merchant's record the loop met first.
            records = records.sorted("id")
            return {
                "id": records[0].id,
                "name": records[0].name,
                "categories": records,
            }

        raw_nodes = {}
        for category in categories:
            top = topmost_listed_ancestor(category)
            node = raw_nodes.setdefault(top.id, {"top": top, "children": []})
            if category.id != top.id:
                node["children"].append(category)

        empty = self.env["product.public.category"]
        merged_tops = {}
        for raw in raw_nodes.values():
            key = _wsc_merge_key(raw["top"].name)
            slot = merged_tops.setdefault(key, {"tops": empty, "children": empty})
            slot["tops"] |= raw["top"]
            for child in raw["children"]:
                slot["children"] |= child

        tree = []
        for slot in merged_tops.values():
            node = merged_entry(slot["tops"])
            child_groups = {}
            for child in slot["children"]:
                child_groups.setdefault(_wsc_merge_key(child.name), empty)
                child_groups[_wsc_merge_key(child.name)] |= child
            node["children"] = sorted(
                (merged_entry(records) for records in child_groups.values()),
                key=lambda entry: (entry["name"] or "").lower(),
            )
            tree.append(node)
        tree.sort(key=lambda entry: (entry["name"] or "").lower())
        return tree

    def _wsc_shop_category_json(self, tree=None):
        """The category tree as JSON for the sidebar's cascading script.

        ``tree`` lets the template reuse the tree it already computed —
        the tree costs a product search, and the sidebar needs it three
        times per render (options, JSON, selected path).
        """
        self.ensure_one()
        if tree is None:
            tree = self._wsc_shop_category_tree()
        return json.dumps(
            [
                {
                    "id": node["id"],
                    "name": node["name"],
                    "children": [
                        {"id": child["id"], "name": child["name"]}
                        for child in node["children"]
                    ],
                }
                for node in tree
            ]
        )

    def _wsc_selected_category_path(self, category, tree=None):
        """Where ``category`` sits in the two-level tree: ``(top_id, sub_id)``.

        Both are REPRESENTATIVE ids: selecting any member of a merged group
        highlights the group's single option. ``sub_id`` is ``None`` when the
        selection IS a top level. Both are ``None`` when nothing is selected
        or the category is not offered by this shop (a hand-typed
        ``?category=`` for another site's category).
        """
        self.ensure_one()
        if not category:
            return (None, None)
        if tree is None:
            tree = self._wsc_shop_category_tree()
        for node in tree:
            if category.id in node["categories"].ids:
                return (node["id"], None)
            for child in node["children"]:
                if category.id in child["categories"].ids:
                    return (node["id"], child["id"])
        return (None, None)

    def _wsc_merged_category_ids(self, category_id):
        """Every category id the option holding ``category_id`` stands for.

        The filter's promise is the LABEL, not the record: asking for
        "Accesorios" must return every merchant's Accesorios, so whoever
        builds a category domain widens the picked id to its whole merged
        group. An id this shop does not offer comes back alone — the domain
        stays valid and the shop's own product domain keeps it harmless.
        """
        self.ensure_one()
        tree = self._wsc_shop_category_tree()
        for node in tree:
            if category_id in node["categories"].ids:
                return node["categories"].ids
            for child in node["children"]:
                if category_id in child["categories"].ids:
                    return child["categories"].ids
        return [category_id]

    def _wsc_zone_sites(self):
        """The marketplace websites the zone switcher offers, portal first.

        Derived from the websites themselves — ``is_marketplace`` plus each
        site's ``marketplace_zone`` and ``domain`` — never from a hardcoded
        list, so opening a fourth neighbourhood shop puts it in the switcher
        by configuration alone. A marketplace without a public domain has no
        address to switch to and is left out.

        sudo on purpose: the switcher publishes nothing that is not already
        public (each site's own URL and zone name), and the public user must
        see the SAME list on every site for the switcher to be symmetric.
        """
        self.ensure_one()
        sites = self.sudo().search(
            [("is_marketplace", "=", True), ("domain", "!=", False)]
        )
        return sites.sorted(
            lambda site: (
                bool(site.marketplace_zone),
                (site._wsc_zone_label() or "").lower(),
            )
        )
