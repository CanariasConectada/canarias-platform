# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestMicrositeRender(TransactionCase):
    """Render the dynamic homepage template against a real company."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create(
            {
                "name": "Render Test Company",
                "street": "Calle Render 5",
                "city": "Telde",
                "zip": "35200",
                "microsite_name": "Render Trade Name",
                "microsite_opening_hours": "L-V 09:00-14:00",
                "microsite_delivery_info": "Island-wide shipping",
                "microsite_about_text": "We render dynamically.",
                "microsite_banner_title": "Closing banner headline",
            }
        )
        cls.website = cls.env["website"].create(
            {
                "name": "Render Test Website",
                "company_id": cls.company.id,
            }
        )
        cls.company.invalidate_recordset(["website_id"])

    def _render_homepage_content(self):
        return str(
            self.env["ir.qweb"]._render(
                "partner_microsite_manager.microsite_homepage_content",
                {"website": self.website},
            )
        )

    def test_homepage_content_renders_company_fields(self):
        html = self._render_homepage_content()
        self.assertIn("Render Trade Name", html)
        self.assertIn("Island-wide shipping", html)
        self.assertIn("We render dynamically.", html)
        self.assertIn("Closing banner headline", html)
        self.assertIn("09:00 - 14:00", html)
        self.assertIn("maps.google.com", html)

    def test_homepage_content_escapes_html(self):
        self.company.microsite_about_text = "<script>alert(1)</script>"
        html = self._render_homepage_content()
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_homepage_content_hides_empty_sections(self):
        self.company.write(
            {
                "microsite_opening_hours": False,
                "microsite_delivery_info": False,
                "microsite_parking_info": False,
                "microsite_about_text": False,
                "microsite_services_text": False,
            }
        )
        html = self._render_homepage_content()
        self.assertNotIn("Opening Hours", html)
        self.assertNotIn("About Us", html)
