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
    """The strip has to close every public page and never appear twice.

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

    def _assert_strip_is_the_last_thing_in_the_footer(self, page):
        """Below the editable footer, the copyright bar and the legal links.

        Whichever of those a site renders (the default site has switched its
        copyright bar off, `partner_microsite_manager` adds legal links at
        priority 110), the strip comes after all of them and nothing but the
        footer's closing tag follows it.
        """
        strip = page.index(FOOTER_CLASS)
        for earlier in ('id="footer"', "o_footer_copyright", "o_pmm_footer_legal"):
            if earlier in page:
                self.assertLess(page.index(earlier), strip, earlier)
        tail = page[strip:]
        tail = tail[tail.index("</div>") + len("</div>") :]
        self.assertEqual(tail.lstrip()[: len("</footer>")], "</footer>")

    # -- present ---------------------------------------------------------------

    def test_the_shop_closes_with_the_strip(self):
        response = self._get("/shop")
        self._assert_strip_count(response, 1)
        self._assert_strip_is_the_last_thing_in_the_footer(response.text)

    def test_a_product_page_closes_with_the_strip(self):
        product = self.env["product.template"].create(
            {
                "name": "Funding Footer Test Product",
                "is_published": True,
                "website_id": self.website.id,
                "list_price": 1.0,
            }
        )
        self._assert_strip_count(self._get(product.website_url), 1)

    def test_a_plain_page_closes_with_the_strip_inside_the_footer(self):
        """Asked for on 2026-09-22: the strip is part of the footer, not a
        band hanging under it.

        A page of its own (no marker in its arch, not the homepage), so the
        assertion is about the layout and nothing else: exactly one strip,
        and it sits between the opening tag of ``footer#bottom`` and the
        closing tag of that same footer -- the LAST ``</footer>`` of the
        page, since the themed sites nest their own ``<footer>`` inside the
        editable area. The login page, whose auth card carries the strip,
        stays without a second one.
        """
        page = self._page_with("<p>Nothing about funding here.</p>")
        response = self._get(page.url)
        self._assert_strip_count(response, 1)
        html = response.text
        strip = html.index(FOOTER_CLASS)
        self.assertLess(html.index('<footer id="bottom"'), strip)
        self.assertLess(strip, html.rindex("</footer>"))
        self._assert_strip_is_the_last_thing_in_the_footer(html)
        login = self._get("/web/login")
        self.assertEqual(login.status_code, 200)
        self.assertNotIn(FOOTER_CLASS, login.text)

    def test_the_band_is_styled_as_the_footer_s_last_row(self):
        """The rules that make it read as part of the footer, from the served
        bundle: a colour of its own, a hairline on top, no margin, and an
        image that fills the width up to 1100px and no further."""
        css = self._stylesheet(self._get("/shop"))
        rule = re.search(r"\.o_cc_funding_footer\s*\{([^}]*)\}", css)
        self.assertTrue(rule, "the band has to have a rule of its own")
        band = re.sub(r"\s+", "", rule.group(1))
        for declaration in ("margin:0", "background-color:#fff", "border-top:1pxsolid"):
            self.assertIn(declaration, band)
        image = re.search(r"\.o_cc_funding_strip_img\s*\{([^}]*)\}", css)
        self.assertTrue(image, "the image has to have a rule of its own")
        image = re.sub(r"\s+", "", image.group(1))
        for declaration in ("width:100%", "max-width:1100px", "height:auto"):
            self.assertIn(declaration, image)

    def _stylesheet(self, response):
        self.assertEqual(response.status_code, 200)
        match = re.search(
            r'href="(/web/assets/[^"]*web\.assets_frontend[^"]*\.css)"', response.text
        )
        self.assertTrue(match, "the page has to load a frontend stylesheet")
        bundle = self.url_open(match.group(1))
        self.assertEqual(bundle.status_code, 200)
        return bundle.text

    def test_the_directory_closes_with_the_strip(self):
        if not self._installed("website_directory"):
            self.skipTest("website_directory not installed")
        self._assert_strip_count(self._get("/comercio"), 1)

    def test_the_events_page_closes_with_the_strip(self):
        if not self._installed("website_event"):
            self.skipTest("website_event not installed")
        self._assert_strip_count(self._get("/event"), 1)

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
