# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import HttpCase, tagged

FLAG = "/website_eu_emblem/static/src/img/eu_flag.svg"
STATEMENT = "Financiado por la Unión Europea – NextGenerationEU"


@tagged("post_install", "-at_install")
class TestEuEmblem(HttpCase):
    """The emblem has to survive whichever header a site happens to use.

    Goes through real HTTP because that is the only way to prove the inherited
    placeholder actually renders inside the header of a live page -- reading
    the template back would only prove the XML parsed.
    """

    def setUp(self):
        super().setUp()
        self.params = self.env["ir.config_parameter"].sudo()

    def _home(self):
        return self.url_open("/").text

    def test_the_flag_is_in_the_page(self):
        self.assertIn(FLAG, self._home())

    def test_the_statement_shows_when_configured(self):
        self.params.set_param("website_eu_emblem.statement", STATEMENT)
        self.assertIn(STATEMENT, self._home())

    def test_without_a_statement_only_the_flag_shows(self):
        """The default state, and the one the grant may not accept.

        Documented as a test rather than left implicit: shipping the emblem
        alone is a deliberate default, not an oversight, and it must stay
        possible until somebody supplies the wording.
        """
        self.params.set_param("website_eu_emblem.statement", "")
        page = self._home()
        self.assertIn(FLAG, page)
        self.assertNotIn("o_cc_eu_emblem_text", page)

    def test_it_can_be_switched_off(self):
        self.params.set_param("website_eu_emblem.enabled", "False")
        self.assertNotIn(FLAG, self._home())

    def test_a_link_is_only_rendered_when_there_is_one(self):
        self.params.set_param("website_eu_emblem.enabled", "True")
        self.params.set_param("website_eu_emblem.url", "")
        self.assertNotIn('<a class="o_cc_eu_emblem"', self._home())

        self.params.set_param("website_eu_emblem.url", "https://example.org/grant")
        self.assertIn("https://example.org/grant", self._home())

    def test_the_emblem_is_the_same_height_as_the_site_logo(self):
        """Asked for on 2026-08-17: "del mismo tamaño que el de los demás".

        It was 1.75rem against the logo's 2.5rem, which read as a smaller,
        secondary mark next to the brand.

        Asserted on the variable rather than on a number: the theme sizes the
        logo with `--logo-height`, so reading it is what keeps the two equal
        when somebody changes the header, and is also what makes the emblem
        shrink with the logo when the header condenses on scroll.
        """
        css = self._stylesheet()
        self.assertIn("height: var(--logo-height, 2.5rem)", css)
        self.assertNotIn("height: 1.75rem", css)

    def _stylesheet(self):
        import re

        page = self.url_open("/")
        self.assertEqual(page.status_code, 200)
        match = re.search(
            r'href="(/web/assets/[^"]*web\.assets_frontend[^"]*\.css)"', page.text
        )
        self.assertTrue(match, "the page has to load a frontend stylesheet")
        bundle = self.url_open(match.group(1))
        self.assertEqual(bundle.status_code, 200)
        return bundle.text
