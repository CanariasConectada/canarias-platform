# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _search_get_detail(self, website, order, options):
        """Widen the ``/shop`` grid's category leaf to the whole merged group.

        The rendered grid does NOT come from ``_get_shop_domain`` (that one
        only bounds the price slider) — it comes from this search-engine
        detail, through ``website._search_with_fuzzy``. Core builds the
        category leaf from ``options['category']`` (a plain numeric string,
        see ``WebsiteSale._get_search_options``), unslugged straight into the
        ONE record id the sidebar sent. Since the sidebar now merges
        same-named categories into one option (see
        ``website._wsc_shop_category_tree``), that one id has to be widened
        to every category the option stands for, exactly like the AJAX
        endpoint already does — otherwise reloading the page would silently
        narrow the grid back to a single merchant's records.
        """
        result = super()._search_get_detail(website, order, options)
        category = options.get("category")
        if not category:
            return result
        category_id = self.env["ir.http"]._unslug(str(category))[1]
        if not category_id:
            return result
        merged_ids = website._wsc_merged_category_ids(category_id)
        if len(merged_ids) <= 1:
            return result
        target = ("public_categ_ids", "child_of", category_id)
        result["base_domain"] = [
            [
                ("public_categ_ids", "child_of", merged_ids) if leaf == target else leaf
                for leaf in domain
            ]
            for domain in result["base_domain"]
        ]
        return result

    def _wsc_owner_company(self):
        """The merchant that owns this product, as one company or empty.

        On this platform a product's ``company_id`` is always empty:
        ``product_multi_company`` keeps ownership in the ``company_ids`` m2m,
        where the marketplace backfill ALSO links the portal's company as an
        extra visibility scope. The owner is therefore the first ACTIVE
        company that is not a marketplace company — the same set
        ``website._marketplace_companies()`` resolves everywhere else.

        (The legacy shop read ``product.company_id.website_id`` directly; that
        field is populated in the old database and empty in this one, which is
        exactly why this helper exists.)

        sudo on purpose: a public visitor cannot read another merchant's
        company record, and the card only prints its trade name and links to
        its public website — both public information.
        """
        self.ensure_one()
        marketplace_ids = self.env["website"]._marketplace_companies().ids
        return self.sudo().company_ids.filtered(
            lambda company: company.active and company.id not in marketplace_ids
        )[:1]

    def _wsc_owner_site_domain(self):
        """The owner's microsite domain, or False when there is none."""
        self.ensure_one()
        owner = self._wsc_owner_company()
        return owner and owner.website_id.sudo().domain or False

    def _wsc_owner_display_name(self):
        """Trade name first, legal name as fallback — like the directory."""
        self.ensure_one()
        owner = self._wsc_owner_company()
        if not owner:
            return False
        partner = owner.partner_id.sudo()
        if "comercial" in partner._fields and partner.comercial:
            return partner.comercial
        return owner.name
