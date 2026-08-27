# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

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

    # ------------------------------------------------------------------
    # Footer social links: website value first, company value as fallback
    # ------------------------------------------------------------------
    _SOCIAL_FIELDS = (
        "social_facebook",
        "social_instagram",
        "social_twitter",
        "social_youtube",
        "social_linkedin",
    )

    def _clear_socials(self):
        # website.social_* defaults from the main company (core behaviour),
        # so both sides are cleared explicitly for a deterministic start.
        empty = dict.fromkeys(self._SOCIAL_FIELDS, False)
        self.website.write(empty)
        self.company.write(empty)

    def test_footer_socials_fall_back_to_the_company(self):
        self._clear_socials()
        self.company.social_instagram = "https://instagram.com/rendershop"
        links = self.website._pmm_footer_social_links()
        self.assertEqual(
            [link["href"] for link in links],
            ["https://instagram.com/rendershop"],
            "A link filled on the company form must reach the footer.",
        )

    def test_footer_socials_website_value_wins(self):
        self._clear_socials()
        self.company.social_facebook = "https://facebook.com/company-value"
        self.website.social_facebook = "https://facebook.com/website-value"
        links = self.website._pmm_footer_social_links()
        self.assertEqual(
            [link["href"] for link in links],
            ["https://facebook.com/website-value"],
            "A hand-typed website value must never be shadowed.",
        )

    def test_footer_socials_render_nothing_when_both_empty(self):
        self._clear_socials()
        self.assertEqual(self.website._pmm_footer_social_links(), [])

    # ------------------------------------------------------------------
    # Opening-hours pill
    # ------------------------------------------------------------------
    def test_opening_hours_render_as_a_collapsible_pill(self):
        html = self._render_homepage_content()
        self.assertIn("o_microsite_hours", html)
        self.assertIn("accordion-button", html)
        self.assertIn("data-microsite-hours", html)
        # The week lives in the collapsed body, one row per open day, each
        # tagged with its weekday index so the browser can bold today.
        self.assertIn('data-hours-row="0"', html)
        self.assertIn('data-hours-row="4"', html)
        self.assertNotIn('data-hours-row="6"', html, "Sunday is closed here.")

    def test_opening_hours_pill_payload_carries_the_whole_week(self):
        pill = self.company._get_microsite_opening_hours_pill()
        payload = json.loads(pill["payload"])
        self.assertEqual(len(payload["days"]), 7, "The browser needs every day.")
        self.assertEqual(payload["days"][0]["ranges"], [["09:00", "14:00"]])
        self.assertEqual(payload["days"][6]["ranges"], [], "Sunday is closed.")
        self.assertTrue(payload["timezone"])
        self.assertTrue(payload["openLabel"] and payload["closedLabel"])

    def test_opening_hours_pill_summary_is_rendered_server_side(self):
        """With JavaScript off the pill must still say something."""
        pill = self.company._get_microsite_opening_hours_pill()
        self.assertTrue(pill["today_label"])
        self.assertTrue(pill["today_text"])
        self.assertIn(pill["today_label"], self._render_homepage_content())

    def test_opening_hours_rows_carry_the_weekday_index(self):
        rows = self.company._get_microsite_opening_hours_rows()
        self.assertEqual([row[0] for row in rows], [0, 1, 2, 3, 4])
        # The legacy pair-shaped helper stays compatible.
        self.assertEqual(
            self.company._get_microsite_opening_hours_lines(),
            [(row[1], row[2]) for row in rows],
        )

    def test_no_opening_hours_renders_no_pill(self):
        self.company.microsite_opening_hours = False
        self.assertEqual(self.company._get_microsite_opening_hours_pill(), {})
        self.assertNotIn("o_microsite_hours", self._render_homepage_content())

    # ------------------------------------------------------------------
    # Contact block: message form + reachable data
    # ------------------------------------------------------------------
    def test_contact_block_renders_the_message_form(self):
        html = self._render_homepage_content()
        self.assertIn('data-model_name="crm.lead"', html)
        self.assertIn('action="/website/form/"', html)
        for field in ("contact_name", "email_from", "phone", "description"):
            self.assertIn(f'name="{field}"', html)
        self.assertIn("s_website_form_send", html)

    def test_form_carries_the_shop_name_as_the_lead_subject(self):
        """crm.lead.name is model-required and is not the visitor's to write."""
        html = self._render_homepage_content()
        self.assertIn('name="name"', html)
        self.assertIn('value="Render Trade Name"', html)

    def test_contact_block_renders_the_map_and_the_address(self):
        html = self._render_homepage_content()
        self.assertIn("maps.google.com", html)
        self.assertIn("Calle Render 5", html)

    def test_contact_block_renders_the_social_links(self):
        # website.social_* defaults from the main company, so both sides are
        # cleared first or the inherited value would win over the shop's.
        self._clear_socials()
        self.company.social_instagram = "https://instagram.com/rendershop"
        html = self._render_homepage_content()
        self.assertIn("https://instagram.com/rendershop", html)
        self.assertIn("fa-instagram", html)

    def test_shop_website_link_is_absolute(self):
        """A bare host in an href would point back into the microsite."""
        self.company.partner_id.website = "rendershop.com"
        self.assertEqual(
            self.company._get_microsite_website_url(), "https://rendershop.com"
        )
        self.assertIn('href="https://rendershop.com"', self._render_homepage_content())

    def test_shop_website_link_keeps_an_explicit_scheme(self):
        self.company.partner_id.website = "http://rendershop.com"
        self.assertEqual(
            self.company._get_microsite_website_url(), "http://rendershop.com"
        )

    def test_no_shop_website_renders_no_link(self):
        self.company.partner_id.website = False
        self.assertEqual(self.company._get_microsite_website_url(), "")
