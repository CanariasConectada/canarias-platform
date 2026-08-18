# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models

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
