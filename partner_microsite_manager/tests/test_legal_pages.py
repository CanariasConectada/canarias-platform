# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re

from odoo.tests import HttpCase, tagged
from odoo.tests.common import TransactionCase

LEGAL_URLS = [
    "/politica-privacidad",
    "/politica-cookies",
    "/terminos-condiciones",
    "/aviso-legal",
]

CANONICAL_ARCH = (
    '<t t-call="website.layout"><div class="container">'
    "<h1>Política de Privacidad</h1>"
    "<p>Texto canónico heredado del legacy, idéntico en muchos sitios.</p>"
    "</div></t>"
)
STUB_ARCH = (
    '<t t-call="website.layout"><div class="container">'
    "<h1>Política de Privacidad</h1>"
    "<p>Contenido de política de privacidad para tiendaficticia.</p>"
    "</div></t>"
)
CUSTOM_ARCH = (
    '<t t-call="website.layout"><div class="container">'
    "<h1>Política de Privacidad</h1>"
    "<p>Texto propio que un comerciante redactó con su asesoría y que nadie"
    " debe pisar, con condiciones particulares de su negocio.</p>"
    "</div></t>"
)


@tagged("post_install", "-at_install")
class TestLegalPagesRender(TransactionCase):
    """The four legal templates render the website company's identity."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create(
            {
                "name": "Comercio Legal SL",
                "vat": "B35000017",
                "street": "Calle Triana 1",
                "city": "Las Palmas de Gran Canaria",
                "zip": "35002",
                "phone": "+34 928 000 000",
                "email": "legal@comerciolegal.example",
            }
        )
        cls.website = cls.env["website"].create(
            {"name": "Comercio Legal", "company_id": cls.company.id}
        )
        cls.blank_company = cls.env["res.company"].create(
            {"name": "Comercio Sin Datos"}
        )
        cls.blank_website = cls.env["website"].create(
            {"name": "Comercio Sin Datos", "company_id": cls.blank_company.id}
        )

    def _render(self, ref, website):
        html = str(
            self.env["ir.qweb"]._render(
                f"partner_microsite_manager.{ref}", {"website": website}
            )
        )
        # Collapse the authoring indentation so assertions read naturally
        return re.sub(r"\s+", " ", html)

    def test_privacy_identity_and_gdpr_sections(self):
        html = self._render("microsite_privacy_policy_content", self.website)
        self.assertIn("Comercio Legal SL", html)
        self.assertIn("B35000017", html)
        self.assertIn("Calle Triana 1", html)
        self.assertIn("legal@comerciolegal.example", html)
        # The GDPR sections the legacy text lacked
        self.assertIn("Agencia Española de Protección de Datos", html)
        self.assertIn("art. 6.1.a RGPD", html)
        self.assertIn("Conservación de los datos", html)
        self.assertIn("prevalecerá la versión en español", html)

    def test_privacy_blank_company_not_broken(self):
        html = self._render("microsite_privacy_policy_content", self.blank_website)
        self.assertIn("Comercio Sin Datos", html)
        # Empty identity fields disappear instead of rendering junk
        self.assertNotIn("NIF/CIF", html)
        self.assertNotIn("False", html)
        self.assertNotIn("None", html)

    def test_cookies_table_matches_reality(self):
        html = self._render("microsite_cookies_policy_content", self.website)
        for cookie_name in (
            "session_id",
            "frontend_lang",
            "website_cookies_bar",
            "odoo_utm_campaign",
        ):
            self.assertIn(cookie_name, html)
        # The legacy claimed Google Analytics; the port must not
        self.assertIn("no utiliza cookies analíticas", html)
        self.assertNotIn("Utilizamos Google Analytics", html)

    def test_terms_identify_merchant(self):
        html = self._render("microsite_terms_conditions_content", self.website)
        self.assertIn("Comercio Legal SL", html)
        self.assertIn("intermediario de información", html)
        self.assertIn("Las Palmas de Gran Canaria", html)
        self.assertIn("prevalecerá la versión en español", html)

    def test_legal_notice_identity_block(self):
        html = self._render("microsite_legal_notice_content", self.website)
        self.assertIn("LSSI-CE", html)
        self.assertIn("Comercio Legal SL", html)
        self.assertIn("B35000017", html)
        blank = self._render("microsite_legal_notice_content", self.blank_website)
        self.assertIn("Comercio Sin Datos", blank)
        self.assertNotIn("NIF/CIF", blank)


@tagged("post_install", "-at_install")
class TestFooterLegalLinks(TransactionCase):
    def test_corporate_footer_links_all_four_pages(self):
        arch = self.env.ref(
            "partner_microsite_manager.microsite_corporate_footer"
        ).arch_db
        for url in LEGAL_URLS:
            self.assertIn(f'href="{url}"', arch)

    def test_platform_footer_links_all_four_pages(self):
        view = self.env.ref("partner_microsite_manager.footer_platform_legal_links")
        for url in LEGAL_URLS:
            self.assertIn(f'href="{url}"', view.arch_db)
        # Only for the websites the corporate footer does not cover
        self.assertIn("not website.is_microsite_themed", view.arch_db)


@tagged("post_install", "-at_install")
class TestLegalPagesHttp(HttpCase):
    """The four global pages answer on a website with no per-site copies."""

    def test_pages_serve_and_footer_links_present(self):
        # Pinned to the website's default language: since the seven-language
        # rollout the anonymous negotiation can land on en_US, and every
        # href then carries the /en/ prefix this test does not assert.
        website = self.env["website"].search([], limit=1)
        self.opener.cookies["frontend_lang"] = website.default_lang_id.code
        for url, marker in [
            ("/politica-privacidad", "Política de Privacidad"),
            ("/politica-cookies", "Política de Cookies"),
            ("/terminos-condiciones", "Términos y Condiciones"),
            ("/aviso-legal", "Aviso Legal"),
        ]:
            response = self.url_open(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertIn(marker, response.text)
            # The test website is not microsite-themed, so every page must
            # carry the platform legal bar in its footer
            self.assertIn('href="/aviso-legal"', response.text, url)


@tagged("post_install", "-at_install")
class TestShadowLegalPageCleanup(TransactionCase):
    """The migration helpers retire shadow pages and keep custom texts."""

    def _make_page(self, website, arch, url="/politica-privacidad"):
        view = self.env["ir.ui.view"].create(
            {
                "name": f"Legal {website.name}",
                "type": "qweb",
                "arch": arch,
                "website_id": website.id,
            }
        )
        return self.env["website.page"].create(
            {
                "name": "Política de Privacidad",
                "url": url,
                "view_id": view.id,
                "website_id": website.id,
                "is_published": True,
            }
        )

    def setUp(self):
        super().setUp()
        # The production copy this suite runs on still holds the per-site
        # legal pages the real migration deliberately KEPT (merchants' own
        # texts). They are data, not fixtures, and they dilute the majority
        # below one half. Retired inside the test transaction only.
        self.env["website.page"].sudo().search(
            [("url", "=", "/politica-privacidad"), ("website_id", "!=", False)]
        ).unlink()
        self.websites = self.env["website"]
        for index in range(5):
            company = self.env["res.company"].create({"name": f"Cleanup Shop {index}"})
            self.websites |= self.env["website"].create(
                {"name": f"Cleanup Shop {index}", "company_id": company.id}
            )

    def test_majority_and_stubs_deleted_custom_kept(self):
        sites = list(self.websites)
        canonical = [self._make_page(site, CANONICAL_ARCH) for site in sites[:3]]
        stub = self._make_page(sites[3], STUB_ARCH)
        custom = self._make_page(sites[4], CUSTOM_ARCH)

        result = self.env["website.page"]._pmm_retire_shadow_legal_pages(min_majority=2)

        self.assertEqual(result["deleted"], 4)
        for page in canonical:
            self.assertFalse(page.exists())
        self.assertFalse(stub.exists())
        self.assertTrue(custom.exists())
        self.assertIn(("/politica-privacidad", sites[4].name), result["kept"])

        # Idempotent: a second run finds nothing left to retire and does not
        # touch the surviving custom page
        again = self.env["website.page"]._pmm_retire_shadow_legal_pages(min_majority=2)
        self.assertEqual(again["deleted"], 0)
        self.assertTrue(custom.exists())

    def test_lonely_custom_page_survives_without_majority(self):
        custom = self._make_page(self.websites[0], CUSTOM_ARCH)
        result = self.env["website.page"]._pmm_retire_shadow_legal_pages(min_majority=2)
        self.assertEqual(result["deleted"], 0)
        self.assertTrue(custom.exists())

    def test_enforce_cookie_consent_everywhere(self):
        for website in self.websites:
            website.write({"cookies_bar": False})
        page_model = self.env["website.page"]

        page_model._pmm_enforce_cookie_consent()

        self.assertFalse(self.env["website"].search([("cookies_bar", "=", False)]))
        self.assertFalse(
            page_model.search(
                [("url", "=", "/cookie-policy"), ("website_id", "!=", False)]
            )
        )
        rewrite = self.env["website.rewrite"].search(
            [("url_from", "=", "/cookie-policy"), ("website_id", "=", False)]
        )
        self.assertEqual(len(rewrite), 1)
        self.assertEqual(rewrite.url_to, "/politica-cookies")
        self.assertEqual(rewrite.redirect_type, "301")

        # Idempotent: no duplicate rewrite, still no stock pages
        page_model._pmm_enforce_cookie_consent()
        self.assertEqual(
            self.env["website.rewrite"].search_count(
                [("url_from", "=", "/cookie-policy"), ("website_id", "=", False)]
            ),
            1,
        )

    def test_enqueue_translations_survives_missing_translator(self):
        count = self.env["website.page"]._pmm_enqueue_legal_translations()
        if "auto.translate.job" in self.env:
            self.assertGreater(count, 0)
        else:
            self.assertEqual(count, 0)
