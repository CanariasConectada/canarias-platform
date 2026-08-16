# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, models

# The four questions a visitor asks in front of a price, in the order they
# ask them. The keys travel in the query string and in the markup, so they
# are stable strings and not ids.
SCOPE_ALL = "all"
SCOPE_ZONE = "zone"
SCOPE_OTHER_ZONE = "other_zone"
SCOPE_SHOP = "shop"


class Website(models.Model):
    _inherit = "website"

    # ------------------------------------------------------------------
    # Which site answers which scope
    # ------------------------------------------------------------------
    # Every scope resolves to a WEBSITE, and the products come from that
    # website's own ``sale_product_domain()``. Nothing here builds a product
    # domain by hand, and that is the whole safety argument for exposing this
    # to anonymous visitors: "the whole platform" is exactly what the portal
    # shop shows, "Guanarteme" is exactly what the Guanarteme shop shows, and
    # if either of those is ever narrowed the comparator narrows with it.
    #
    # `website_sale_marketplace` is what makes this true: the portal is a
    # marketplace with no zone, each neighbourhood is a marketplace with one,
    # and a merchant microsite is neither.

    def _comparison_portal_website(self):
        """The site that shows the whole platform.

        Found by what it IS rather than by id: company 1 owns two websites
        (the portal and the Admin Portal), so ``company.website_id`` is
        ambiguous, while "marketplace with no zone" is the definition the
        aggregated shop already runs on.
        """
        return (
            self.env["website"]
            .sudo()
            .search(
                [
                    ("is_marketplace", "=", True),
                    "|",
                    ("marketplace_zone", "=", False),
                    ("marketplace_zone", "=", ""),
                ],
                limit=1,
            )
        )

    def _comparison_zone_websites(self):
        """The neighbourhood shops, in a stable order."""
        return (
            self.env["website"]
            .sudo()
            .search(
                [
                    ("is_marketplace", "=", True),
                    ("marketplace_zone", "not in", [False, ""]),
                ],
                order="id",
            )
        )

    def _comparison_current_zone(self):
        """The neighbourhood the visitor is standing in, or False.

        A zone shop says so itself; a merchant microsite says it through the
        shop's own company. The portal is in no neighbourhood, and answering
        "canarias" there would be a zone that has no shop behind it.
        """
        self.ensure_one()
        if self.marketplace_zone:
            return self.marketplace_zone
        company = self.company_id.sudo()
        zone = getattr(company, "commercial_zone", False)
        return zone if zone and zone != "canarias" else False

    def _comparison_owner_website(self, product):
        """The site of the shop that actually sells ``product``.

        "The same shop" has to mean the merchant's shop even when the visitor
        is standing on the portal, where every shop's products are mixed
        together -- that is precisely where the question gets asked.

        The marketplace companies are subtracted rather than the merchant
        looked up: ``website_sale_marketplace`` adds the portal company to
        every product's ``company_ids`` so the aggregated shop can see it, and
        the zone companies are added by ``zone_company_ownership``. What is
        left is the merchant.
        """
        if not product:
            return self.env["website"]
        marketplaces = (
            self.env["website"]
            .sudo()
            .search([("is_marketplace", "=", True)])
            .company_id
        )
        owners = product.sudo().company_ids - marketplaces
        for owner in owners:
            site = owner.website_id
            # A marketplace is never "the same shop", even if one slipped
            # through the subtraction above: the whole scope exists to name
            # the merchant.
            if site and not site.is_marketplace:
                return site.sudo()
        return self.env["website"]

    def _comparison_scope_website(self, scope, zone=None, product=None):
        """The site whose shop answers ``scope``, or an empty recordset.

        Empty means "not available here", and the caller falls back rather
        than guessing: a scope the visitor cannot have is better refused than
        quietly answered with somebody else's catalogue.
        """
        self.ensure_one()
        if scope == SCOPE_ALL:
            return self._comparison_portal_website()
        if scope == SCOPE_SHOP:
            return self._comparison_owner_website(product)
        if scope in (SCOPE_ZONE, SCOPE_OTHER_ZONE):
            key = zone if scope == SCOPE_OTHER_ZONE else self._comparison_current_zone()
            if not key:
                return self.env["website"]
            return self._comparison_zone_websites().filtered(
                lambda site: site.marketplace_zone == key
            )[:1]
        return self.env["website"]

    # ------------------------------------------------------------------
    # What to offer the visitor
    # ------------------------------------------------------------------
    def _comparison_scopes(self, product=None):
        """The scopes worth showing here, as data for the picker.

        A scope is only offered when a site is behind it. On the portal there
        is no "this neighbourhood", and on a shop with no other neighbourhood
        configured there is no "another one" -- offering either would be a tab
        that comes back empty.
        """
        self.ensure_one()
        scopes = []
        portal = self._comparison_portal_website()
        if portal:
            scopes.append(
                {
                    "key": SCOPE_ALL,
                    "label": _("Toda Canarias Conectada"),
                    "zones": [],
                }
            )
        current_zone = self._comparison_current_zone()
        zone_sites = self._comparison_zone_websites()
        current_site = zone_sites.filtered(
            lambda site: site.marketplace_zone == current_zone
        )[:1]
        if current_site:
            scopes.append(
                {
                    "key": SCOPE_ZONE,
                    "label": _("Mi zona comercial: %s", current_site.name),
                    "zones": [],
                }
            )
        others = zone_sites - current_site
        if others:
            scopes.append(
                {
                    "key": SCOPE_OTHER_ZONE,
                    "label": _("Otra zona comercial"),
                    "zones": [
                        {"key": site.marketplace_zone, "name": site.name}
                        for site in others
                    ],
                }
            )
        owner = self._comparison_owner_website(product)
        if owner:
            scopes.append(
                {
                    "key": SCOPE_SHOP,
                    "label": _("Solo en %s", owner.name),
                    "zones": [],
                }
            )
        return scopes

    def _comparison_default_scope(self, product=None):
        """Open on the narrowest scope the visitor is actually inside.

        Somebody looking at a jacket in a shop wants that shop's other
        jackets first; the whole platform is one click away and is a much
        longer list.
        """
        self.ensure_one()
        available = [scope["key"] for scope in self._comparison_scopes(product)]
        for candidate in (SCOPE_SHOP, SCOPE_ZONE, SCOPE_ALL):
            if candidate in available:
                return candidate
        return SCOPE_ALL
