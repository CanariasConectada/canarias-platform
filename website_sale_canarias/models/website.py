# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo import models
from odoo.fields import Domain


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
        """The shop's categories in two levels, nothing pruned.

        Same category SET as ``_wsc_shop_categories`` — this only changes the
        shape. Each category hangs under its topmost ancestor that is itself
        part of the set; a category whose ancestors sell nothing here becomes
        a top level of its own. Deeper chains are flattened to the second
        level, so every category the flat sidebar listed is still offered:
        either as a main category or as a subcategory of one.

        Returns a list of ``{"category": record, "children": [records]}``
        nodes, both levels sorted alphabetically like the flat list was.
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

        nodes = {}
        for category in categories:
            top = topmost_listed_ancestor(category)
            node = nodes.setdefault(top.id, {"category": top, "children": []})
            if category.id != top.id:
                node["children"].append(category)
        tree = sorted(
            nodes.values(),
            key=lambda node: (node["category"].name or "").lower(),
        )
        for node in tree:
            node["children"].sort(key=lambda child: (child.name or "").lower())
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
                    "id": node["category"].id,
                    "name": node["category"].name,
                    "children": [
                        {"id": child.id, "name": child.name}
                        for child in node["children"]
                    ],
                }
                for node in tree
            ]
        )

    def _wsc_selected_category_path(self, category, tree=None):
        """Where ``category`` sits in the two-level tree: ``(top_id, sub_id)``.

        ``sub_id`` is ``None`` when the selection IS a top level. Both are
        ``None`` when nothing is selected or the category is not offered by
        this shop (a hand-typed ``?category=`` for another site's category).
        """
        self.ensure_one()
        if not category:
            return (None, None)
        if tree is None:
            tree = self._wsc_shop_category_tree()
        for node in tree:
            if node["category"].id == category.id:
                return (category.id, None)
            if category.id in [child.id for child in node["children"]]:
                return (node["category"].id, category.id)
        return (None, None)

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
