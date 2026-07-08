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
