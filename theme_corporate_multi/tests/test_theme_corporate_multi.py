# Copyright 2026 Canarias Conectada
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo.tests import HttpCase, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCertificationBadges(TransactionCase):
    """The footer badges must agree with the certification, always."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "Comercio de prueba tema"})
        cls.website = cls.env["website"].create(
            {"name": "Sitio de prueba tema", "company_id": cls.company.id}
        )

    def test_no_certification_shows_no_badge(self):
        certs = self.website.get_certifications()
        self.assertFalse(certs["has_silver"])
        self.assertFalse(certs["has_sostenible"])

    def test_level_none_is_not_a_certification(self):
        """``none`` is a real stored value, not an absent one.

        Treating it as truthy would badge every company that ever opened the
        questionnaire without finishing it.
        """
        if "silver_certification_level" not in self.company._fields:
            self.skipTest("silver_economy no está instalado")
        self.company.silver_certification_level = "none"
        self.assertFalse(self.website.get_certifications()["has_silver"])

    def test_every_awarded_level_shows_the_badge(self):
        if "silver_certification_level" not in self.company._fields:
            self.skipTest("silver_economy no está instalado")
        for level in ("bronze", "silver", "gold"):
            self.company.silver_certification_level = level
            self.assertTrue(
                self.website.get_certifications()["has_silver"],
                f"el nivel {level} debería mostrar el sello",
            )

    def test_a_missing_vertical_module_does_not_break_the_footer(self):
        """The footer renders on installations without the vertical modules.

        ``get_certifications`` is called on every page of every microsite, so a
        missing field has to mean "no badge", never a traceback.
        """
        certs = self.website.get_certifications()
        self.assertIn("has_silver", certs)
        self.assertIn("has_sostenible", certs)

    def test_a_website_with_no_company_does_not_break_the_footer(self):
        self.website.company_id = False
        certs = self.website.get_certifications()
        self.assertFalse(certs["has_silver"])
        self.assertFalse(certs["has_sostenible"])

    def test_footer_year_is_the_current_one(self):
        """Guards the bug this port fixes: the year used to be hard-coded."""
        from odoo import fields

        self.assertEqual(
            self.website.get_footer_year(), fields.Date.context_today(self.website).year
        )


@tagged("post_install", "-at_install")
class TestLegalPageOwnership(TransactionCase):
    """This theme must not compete with partner_microsite_manager."""

    def test_the_theme_publishes_no_legal_page(self):
        """The original module shipped its own /politica-privacidad and friends.

        Two ``website.page`` records on the same URL let Odoo pick either one,
        so the real legal text — the one naming the company and its tax number —
        could be replaced by a generic copy without anybody noticing.
        """
        pages = self.env["ir.model.data"].search(
            [("module", "=", "theme_corporate_multi"), ("model", "=", "website.page")]
        )
        self.assertFalse(
            pages,
            "theme_corporate_multi no debe publicar páginas: las legales son de "
            "partner_microsite_manager",
        )

    def test_the_legal_pages_still_have_exactly_one_owner(self):
        Page = self.env["website.page"].with_context(active_test=False)
        for url in (
            "/politica-privacidad",
            "/politica-cookies",
            "/terminos-condiciones",
        ):
            shared = Page.search([("url", "=", url), ("website_id", "=", False)])
            self.assertLessEqual(
                len(shared), 1, f"hay más de una página compartida en {url}"
            )


@tagged("post_install", "-at_install")
class TestCorporateLayout(HttpCase):
    def test_the_footer_renders_on_the_homepage(self):
        response = self.url_open("/")
        self.assertEqual(response.status_code, 200)
        body = response.text
        # The links the footer is legally required to carry.
        self.assertIn("/politica-privacidad", body)
        self.assertIn("/aviso-legal", body)
        # And the year, which used to be frozen at 2025.
        from odoo import fields

        self.assertIn(str(fields.Date.context_today(self.env.user).year), body)
