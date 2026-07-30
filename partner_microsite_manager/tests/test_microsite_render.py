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

    # -- public phones --------------------------------------------------------
    def test_public_phone_wins_over_the_partner_phone(self):
        # The shop publishes its counter line; the partner record keeps the
        # administrative one. Showing the latter is what the origin never did.
        self.company.partner_id.phone = "928000000"
        self.company.microsite_phone = "928111111"
        html = self._render_homepage_content()
        self.assertIn("928111111", html)
        self.assertNotIn("928000000", html)

    def test_partner_phone_is_the_fallback(self):
        self.company.partner_id.phone = "928000000"
        self.company.microsite_phone = False
        html = self._render_homepage_content()
        self.assertIn("928000000", html)

    def test_second_phone_renders_below_the_first(self):
        self.company.microsite_phone = "928111111"
        self.company.microsite_phone2 = "603222222"
        html = self._render_homepage_content()
        self.assertIn("928111111", html)
        self.assertIn("603222222", html)
        self.assertLess(html.index("928111111"), html.index("603222222"))

    def test_no_phone_at_all_renders_no_phone_line(self):
        self.company.partner_id.phone = False
        self.company.write({"microsite_phone": False, "microsite_phone2": False})
        html = self._render_homepage_content()
        self.assertNotIn("fa-phone", html)

    def test_second_phone_alone_is_still_shown(self):
        # phone2 does not depend on phone1 at render time: the form hides the
        # field when the first is empty, but data migrated from the origin
        # must never vanish because of a UI rule.
        self.company.partner_id.phone = False
        self.company.microsite_phone = False
        self.company.microsite_phone2 = "603222222"
        html = self._render_homepage_content()
        self.assertIn("603222222", html)
