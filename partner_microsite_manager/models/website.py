# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models
from odoo.exceptions import AccessError

# Badge accent colour per certification level, mirrored in the microsite
# footer pills so they read the same as the certification showcase section.
_CERT_LEVEL_COLORS = {
    "gold": "#FFD700",
    "silver": "#C0C0C0",
    "bronze": "#CD7F32",
}

# Networks shown in the microsite footer, in display order. Field name on
# both website and res.company (the ``social_media`` module, a base
# dependency of ``website``, defines the company side), visible title and
# FontAwesome icon class.
_FOOTER_SOCIAL_NETWORKS = (
    ("social_facebook", "Facebook", "fa-facebook"),
    ("social_instagram", "Instagram", "fa-instagram"),
    ("social_twitter", "X/Twitter", "fa-twitter"),
    ("social_youtube", "YouTube", "fa-youtube-play"),
    ("social_linkedin", "LinkedIn", "fa-linkedin"),
)


class Website(models.Model):
    _inherit = "website"

    # Whether the caller may open the two screens the shops list offers
    # besides the content editor. Computed rather than assumed: reading
    # orders needs the sales groups and reading pages needs
    # `website_seo_restricted_editor`, and neither is a dependency of this
    # module -- a button that raises AccessError is worse than no button.
    merchant_can_open_orders = fields.Boolean(
        compute="_compute_merchant_can_open", string="Orders reachable"
    )
    merchant_can_open_pages = fields.Boolean(
        compute="_compute_merchant_can_open", string="Pages reachable"
    )

    def _compute_merchant_can_open(self):
        orders = self._pmm_has_access("sale.order", "read")
        pages = self._pmm_has_access("website.page", "write")
        for website in self:
            website.merchant_can_open_orders = orders
            website.merchant_can_open_pages = pages

    def _pmm_has_access(self, model_name, operation):
        """True when the caller may ``operation`` on ``model_name``.

        Guards the model's very existence too: both are soft dependencies.
        """
        if model_name not in self.env:
            return False
        try:
            return self.env[model_name].has_access(operation)
        except Exception:  # noqa: BLE001 - a missing right is not an error here
            return False

    def _pmm_assert_own_site(self):
        """Refuse a site that is not the caller's own shop.

        The list is built from the caller's own companies, but a button
        carries an id and an id can be edited, so the check belongs here and
        not only in the action that produced the row.
        """
        self.ensure_one()
        allowed = self.env["res.company"]._get_own_microsite_companies()
        allowed |= self.env["res.company"]._get_own_microsite_company()
        if self.env.user.has_group("base.group_erp_manager"):
            return
        if self.company_id not in allowed:
            raise AccessError(_("That website does not belong to your shop."))

    def action_microsite_content(self):
        """The page-content editor of this site's shop, no picker in front."""
        self._pmm_assert_own_site()
        return {
            "type": "ir.actions.act_window",
            "name": _("Page content"),
            "res_model": "microsite.content.editor",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {"microsite_company_id": self.company_id.id},
        }

    def action_microsite_orders(self):
        """The orders placed on this site."""
        self._pmm_assert_own_site()
        return {
            "type": "ir.actions.act_window",
            "name": _("Orders"),
            "res_model": "sale.order",
            "view_mode": "list,form",
            "views": [(False, "list"), (False, "form")],
            "domain": [("website_id", "=", self.id)],
            "context": {"create": False},
        }

    def action_microsite_pages(self):
        """The pages of this site, where the SEO dialog is saved from."""
        self._pmm_assert_own_site()
        return {
            "type": "ir.actions.act_window",
            "name": _("Pages"),
            "res_model": "website.page",
            "view_mode": "list,form",
            "views": [(False, "list"), (False, "form")],
            "domain": [("website_id", "=", self.id)],
            "context": {"create": False, "delete": False},
        }

    # Explicit, per-website switch that turns on the corporate microsite look
    # (black footer, legal links). Off by default so the directory / main
    # website keep the standard Odoo footer untouched.
    is_microsite_themed = fields.Boolean(
        string="Corporate Microsite Look",
        default=False,
        help="Render the corporate microsite footer (black footer with "
        "social links, legal pages and certification badges) on this "
        "website. Leave off for the directory and the main website.",
    )

    def _pmm_footer_social_links(self):
        """Social links for the microsite footer, per network, with fallback.

        The website value wins; when it is empty the owning COMPANY's value
        fills in. Rationale (measured at the origin, see the migration
        script ``website_social_from_company.py``): the legacy footer read
        only ``website.social_*`` while merchants filled the links on the
        company form, so correct values sat there invisible. Falling back
        per network keeps a hand-typed website value untouched and still
        renders nothing when both sides are empty.

        Rendered in a public (sudo) website context.
        """
        self.ensure_one()
        company = self.company_id.sudo()
        links = []
        for field_name, title, icon in _FOOTER_SOCIAL_NETWORKS:
            href = self[field_name] or company[field_name]
            if href:
                links.append({"href": href, "title": title, "icon": icon})
        return links

    def _pmm_own_website_link(self):
        """The owning company's OWN site as a footer link, or ``None``.

        Core ``res.company.website`` (client request 2026-09-16: "falta un
        espacio en donde podamos colocar el website de las personas"). Not
        the microsite's own address: that is ``website.domain``. The title
        is the host, which is what a visitor wants to know before leaving.
        """
        self.ensure_one()
        company = self.company_id.sudo()
        href = company._get_microsite_website_url()
        if not href:
            return None
        return {
            "href": href,
            "title": company._get_microsite_website_host() or href,
            "icon": "fa-globe",
        }

    def _pmm_footer_links(self):
        """The footer's icon row: the shop's own site first, then the networks."""
        self.ensure_one()
        own = self._pmm_own_website_link()
        return ([own] if own else []) + self._pmm_footer_social_links()

    def _pmm_footer_certifications(self):
        """Certification badges to show in the microsite footer.

        Reads the certification status from the ``company_certification``
        module when it is installed; returns an empty list otherwise, so
        this module keeps depending only on ``website``. Rendered in a
        public (sudo) website context.
        """
        self.ensure_one()
        if "res.company.certification" not in self.env:
            return []
        company = self.company_id.sudo()
        if not hasattr(company, "_get_valid_certifications"):
            return []
        badges = []
        for cert in company._get_valid_certifications():
            badges.append(
                {
                    "name": cert.type_id.name,
                    "level_label": cert._get_level_label(),
                    "color": _CERT_LEVEL_COLORS.get(cert.level, "#6c757d"),
                }
            )
        return badges
