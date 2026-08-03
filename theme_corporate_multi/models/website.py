# Copyright 2026 Canarias Conectada
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models

# A company is shown as certified only from these levels up. ``none`` and a
# missing value both mean "not certified"; the intermediate levels are the ones
# silver_economy and sustainability award.
_CERTIFIED_LEVELS = ("bronze", "silver", "gold")


class Website(models.Model):
    _inherit = "website"

    def get_footer_year(self):
        """Current year for the copyright line.

        QWeb does not expose ``datetime`` in Odoo 19, and the original theme
        worked around that by hard-coding "© 2025" — which then went stale on
        every page of 200+ public sites. Asking the model keeps it honest.
        """
        return fields.Date.context_today(self).year

    def get_certifications(self):
        """Silver / sustainability badges for the footer of this microsite.

        The original theme read these from ``ir.config_parameter`` keys named
        ``website.<id>.has_silver`` and ``website.<id>.has_sostenible``, written
        by hand. That is a copy of the truth, and it drifted: a company whose
        certification expired, was revoked or was awarded through the backend
        kept whatever the parameter said, forever.

        The real owners are ``silver_economy`` and ``sustainability``, which
        each compute a level on the company. Reading them directly means the
        badge cannot disagree with the certification any more.
        """
        self.ensure_one()
        company = self.company_id
        return {
            "has_silver": self._has_certification(
                company, "silver_certification_level"
            ),
            "has_sostenible": self._has_certification(
                company, "sustain_certification_level"
            ),
        }

    def _has_certification(self, company, field_name):
        """Read one certification level defensively.

        The field only exists when its vertical module is installed. This theme
        must render the footer on an installation that has neither, so a missing
        field means "no badge", not a traceback on every page.
        """
        if not company or field_name not in company._fields:
            return False
        return company[field_name] in _CERTIFIED_LEVELS
