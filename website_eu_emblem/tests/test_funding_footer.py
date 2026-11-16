# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re
from urllib.parse import urlsplit

from odoo.tests import HttpCase, tagged

STRIP = "/website_eu_emblem/static/src/img/funding_strip.png"
FOOTER_CLASS = "o_cc_funding_footer"
MICROSITE_TEMPLATE = "partner_microsite_manager.microsite_homepage_content"


@tagged("post_install", "-at_install")
class TestFundingFooter(HttpCase):
    """The strip has to be the first row of the footer of every public page
    and never appear twice.

    Through real HTTP: the condition depends on the request path and on the
    page object the layout receives, both of which only exist in a served
    request.
    """

    def setUp(self):
        super().setUp()
        self.website = self.env["website"].get_current_website()

    def _installed(self, module):
        return bool(
            self.env["ir.module.module"].search_count(
                [("name", "=", module), ("state", "=", "installed")]
            )
        )

    def _get(self, path, host=None, hops=5):
        """GET following redirects WITHOUT leaving the test server.

        The validation copy carries the production domains: a canonical
        redirect there points at ``https://<site>.canariasconectada.es/...``,
        which ``requests`` would happily follow to the live platform. Only
        the path (and the ``/en/`` language prefix) of each hop is kept.
        """
        headers = {"Host": host} if host else None
        for _ in range(hops):
            response = self.url_open(path, headers=headers, allow_redirects=False)
            if response.status_code not in (301, 302, 303, 307, 308):
                return response
            target = urlsplit(response.headers["Location"])
            path = target.path + (f"?{target.query}" if target.query else "")
        self.fail(f"too many redirects for {path}")

    def _assert_strip_count(self, response, expected):
        self.assertEqual(response.status_code, 200, response.url)
        page = response.text
        self.assertEqual(page.count(STRIP), expected, response.url)
        self.assertEqual(page.count(FOOTER_CLASS), expected, response.url)

    def _assert_strip_is_above_the_footer_content(self, page):
        """The strip is the first row of ``footer#bottom``.

        It comes after the footer's opening tag and before ``div#footer``
        (the site's own footer content), which every page renders. The
        copyright bar and the legal links are optional (the default site has
        switched its copyright bar off, `partner_microsite_manager` adds the
        legal links at priority 110); whichever of them a page renders comes
        after the strip as well.
        """
        strip = page.index(FOOTER_CLASS)
        self.assertLess(page.index('<footer id="bottom"'), strip)
        footer = re.search(r'<div[^>]*\bid="footer"', page)
        self.assertTrue(footer, "the page has to render div#footer")
        self.assertLess(strip, footer.start())
        for marker in ("o_footer_copyright", "o_pmm_footer_legal"):
            if marker in page:
                self.assertLess(strip, page.index(marker), marker)

    # -- present ---------------------------------------------------------------

    def test_the_shop_shows_the_strip_as_the_first_row_of_the_footer(self):
        response = self._get("/shop")
        self._assert_strip_count(response, 1)
        self._assert_strip_is_above_the_footer_content(response.text)

    def test_a_product_page_shows_the_strip_as_the_first_row_of_the_footer(self):
        product = self.env["product.template"].create(
            {
                "name": "Funding Footer Test Product",
                "is_published": True,
                "website_id": self.website.id,
                "list_price": 1.0,
            }
        )
        response = self._get(product.website_url)
        self._assert_strip_count(response, 1)
        self._assert_strip_is_above_the_footer_content(response.text)

    def test_a_plain_page_shows_the_strip_as_the_first_row_of_the_footer(self):
        """A page of its own (no marker in its arch, not the homepage), so
        the assertion is about the layout and nothing else: exactly one
        strip, rendered as the first row of ``footer#bottom``. The login
        page, whose auth card carries the strip, stays without a second one.
        """
        page = self._page_with("<p>Nothing about funding here.</p>")
        response = self._get(page.url)
        self._assert_strip_count(response, 1)
        self._assert_strip_is_above_the_footer_content(response.text)
        login = self._get("/web/login")
        self.assertEqual(login.status_code, 200)
        self.assertNotIn(FOOTER_CLASS, login.text)

    def test_the_band_is_styled_as_the_first_row_of_the_footer(self):
        """The rules that make it read as part of the footer, from the served
        bundle: a colour of its own, a hairline on each side, no margin, and
        an image that fills the width up to 1100px and no further.

        Each declaration is matched up to its terminator (``;`` or the end of
        the rule), with the compiled whitespace stripped, so ``margin:0``
        cannot be satisfied by ``margin:0 auto``.
        """
        css = self._stylesheet(self._get("/shop"))
        self._assert_declarations(
            css,
            "o_cc_funding_footer",
            (
                "margin:0",
                "background-color:#fff",
                r"border-top:1pxsolidrgba\(0,0,0,0?\.08\)",
                r"border-bottom:1pxsolidrgba\(0,0,0,0?\.08\)",
            ),
        )
        self._assert_declarations(
            css,
            "o_cc_funding_strip_img",
            ("width:100%", "max-width:1100px", "height:auto"),
        )

    def _assert_declarations(self, css, selector, declarations):
        rule = re.search(r"\." + re.escape(selector) + r"\s*\{([^}]*)\}", css)
        self.assertTrue(rule, f".{selector} has to have a rule of its own")
        body = re.sub(r"\s+", "", rule.group(1)) + ";"
        for declaration in declarations:
            self.assertRegex(body, "(^|;)" + declaration + ";", declaration)

    def _stylesheet(self, response):
        self.assertEqual(response.status_code, 200)
        match = re.search(
            r'href="(/web/assets/[^"]*web\.assets_frontend[^"]*\.css)"', response.text
        )
        self.assertTrue(match, "the page has to load a frontend stylesheet")
        bundle = self.url_open(match.group(1))
        self.assertEqual(bundle.status_code, 200)
        return bundle.text

    def test_the_directory_shows_the_strip_as_the_first_row_of_the_footer(self):
        if not self._installed("website_directory"):
            self.skipTest("website_directory not installed")
        response = self._get("/comercio")
        self._assert_strip_count(response, 1)
        self._assert_strip_is_above_the_footer_content(response.text)

    def test_the_events_page_shows_the_strip_as_the_first_row_of_the_footer(self):
        if not self._installed("website_event"):
            self.skipTest("website_event not installed")
        response = self._get("/event")
        self._assert_strip_count(response, 1)
        self._assert_strip_is_above_the_footer_content(response.text)

    # -- absent ----------------------------------------------------------------

    def test_the_login_page_keeps_only_the_card_strip(self):
        """``website_login_branding`` puts the strip inside the auth card."""
        response = self._get("/web/login")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(STRIP, response.text)
        self.assertNotIn(FOOTER_CLASS, response.text)

    def test_a_page_that_already_shows_the_strip_gets_no_second_one(self):
        page = self._page_with(
            '<img src="/web/image/952/logos_subvenciones.png" alt="Subvenciones"/>'
        )
        response = self._get(page.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("/web/image/952/logos_subvenciones.png", response.text)
        self.assertNotIn(STRIP, response.text)
        self.assertNotIn(FOOTER_CLASS, response.text)

    def test_a_microsite_homepage_gets_no_second_one(self):
        """The dynamic microsite template already renders the strip."""
        if not self._installed("partner_microsite_manager"):
            self.skipTest("partner_microsite_manager not installed")
        page = self._page_with(f'<t t-call="{MICROSITE_TEMPLATE}"/>')
        self.assertFalse(self.website._cc_show_funding_footer(page))
        response = self._get(page.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(STRIP, response.text)
        self.assertNotIn(FOOTER_CLASS, response.text)

    def test_the_helper_is_conservative_about_what_it_receives(self):
        self.assertTrue(self.website._cc_show_funding_footer(None))
        self.assertTrue(self.website._cc_show_funding_footer(self.website))

    def _page_with(self, body):
        return self.env["website.page"].create(
            {
                "name": "Funding footer test page",
                "url": "/cc-funding-footer-test",
                "is_published": True,
                "website_id": self.website.id,
                "type": "qweb",
                "key": "website_eu_emblem.test_funding_footer_page",
                "arch": (
                    '<t t-call="website.layout">'
                    f'<div id="wrap" class="oe_structure">{body}</div>'
                    "</t>"
                ),
            }
        )
