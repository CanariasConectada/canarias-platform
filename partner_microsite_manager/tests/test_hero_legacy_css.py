# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re

from odoo.modules.module import get_module_path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import render_homepage_for

SCSS = "static/src/scss/microsite_hero_legacy.scss"


@tagged("post_install", "-at_install")
class TestHeroLegacyCss(TransactionCase):
    """The legacy hero rule reaches the imported heroes and no other section.

    The dynamic hero is ALSO `section.s_cover[data-name="Hero"]`; only the
    `:not(.o_pmm_hero)` in the selector keeps it on its own stylesheet.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with open(
            "%s/%s" % (get_module_path("partner_microsite_manager"), SCSS),
            encoding="utf-8",
        ) as handle:
            cls.scss = handle.read()

    def test_the_selector_is_scoped_to_the_imported_heroes(self):
        selector = re.search(r"\$o-pmm-legacy-hero:\s*'([^']*)'", self.scss)
        self.assertTrue(selector, "the selector variable is the rule's contract")
        parts = [part.strip() for part in selector.group(1).split(",")]
        self.assertEqual(
            parts,
            [
                'section.s_cover[data-name="Hero"]:not(.o_pmm_hero)',
                'section.s_adventure[data-name="Portada"]',
            ],
        )

    def test_the_strip_selector_is_scoped_to_sec1_and_separador(self):
        selector = re.search(r"\$o-pmm-legacy-strip:\s*'([^']*)'", self.scss)
        self.assertTrue(selector, "the strip selector variable is the rule's contract")
        parts = [part.strip() for part in selector.group(1).split(",")]
        self.assertEqual(
            parts,
            [
                'section.s_kickoff[data-name="SEC1"]',
                'section.s_kickoff[data-name="Separador"]',
            ],
        )
        for part in parts:
            self.assertNotIn("Hero", part, "the hero rule owns the heroes")
            self.assertNotIn("Portada", part, "the hero rule owns the heroes")

    def test_the_strip_rule_is_written_through_the_variable(self):
        # The first top-level block opened on the variable, up to its own
        # closing brace: the strip rule has no nested block.
        block = re.search(
            r"^#\{\$o-pmm-legacy-strip\} \{\n(.*?)^\}", self.scss, re.S | re.M
        )
        self.assertTrue(block, "the strip rule is written through the variable")
        self.assertRegex(
            block.group(1),
            r"background-attachment:\s*scroll\s*!important;",
            "the attachment is forced inside the strip block",
        )

    def test_the_dynamic_hero_is_what_the_rule_excludes(self):
        company = self.env["res.company"].create({"name": "Excluded Shop"})
        html = render_homepage_for(self.env, company)
        hero = re.search(r'<section[^>]*data-name="Hero"[^>]*>', html)
        self.assertTrue(hero, "the dynamic homepage opens with a Hero section")
        classes = re.search(r'class="([^"]*)"', hero.group(0)).group(1).split()
        self.assertIn("s_cover", classes, "same snippet class as the imported heroes")
        self.assertIn("o_pmm_hero", classes, "the class the legacy rule excludes")
