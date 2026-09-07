# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""The sidebar must render in Spanish.

Reported 2026-08-26: the sidebar came out in English on every site. The
sidebar had moved from ``directory_index`` into its own template
(``directory_sidebar``) but ``i18n/es.po`` still attached its terms to the
old view: Odoo binds ``model_terms`` translations to the record named in
the ``#:`` line, so they never reached the new one.
"""

import os
import re

from odoo.modules.module import get_module_path
from odoo.tests import TransactionCase, tagged

SIDEBAR_TERMS = (
    "All zones",
    "All categories",
    "All subcategories",
    "All specialties",
    "Commercial Zone",
    "Main category",
    "Subcategory",
    "Specialty",
    "Filtering by:",
    ">Category",
)
# The selected-filter chip every section calls. A STATIC text node on
# purpose: QWeb hands an expression attribute (t-attf-aria-label) to the
# translator as "Remove filter: {{0}}", so the words a screen reader
# announces would never come back translated. It lives in its own template,
# so it is bound there and not to the sidebar.
REMOVE_TERM = '<span class="visually-hidden">Remove filter</span>'
REMOVE_TERM_ES = '<span class="visually-hidden">Quitar filtro</span>'
RESULT_TERMS = ("No businesses found", "Try another search term")


def _po_entries(path):
    """(msgid, [references]) pairs of a .po file, stdlib only.

    Inner double quotes come back unescaped, so a msgid built from markup
    can be compared against the markup as it is written in the template.
    """
    entries = []
    refs, msgid, in_msgid = [], [], False
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if line.startswith("#:"):
                refs.append(line[2:].strip())
            elif line.startswith("msgid "):
                msgid, in_msgid = [line[6:]], True
            elif line.startswith("msgstr"):
                if in_msgid:
                    text = "".join(part.strip('"') for part in msgid)
                    entries.append((text.replace('\\"', '"'), refs))
                refs, in_msgid = [], False
            elif in_msgid and line.startswith('"'):
                msgid.append(line)
    return entries


@tagged("post_install", "-at_install")
class TestSidebarTranslations(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.po_path = os.path.join(
            get_module_path("website_directory"), "i18n", "es.po"
        )

    def test_es_po_refs_point_at_the_sidebar_template(self):
        entries = _po_entries(self.po_path)
        self.assertTrue(entries, "es.po parsed empty")
        for term in SIDEBAR_TERMS:
            matching = [
                refs for msgid, refs in entries if term in msgid.replace("\\n", "")
            ]
            self.assertTrue(matching, f"no es.po entry for {term!r}")
            for refs in matching:
                self.assertTrue(
                    any(
                        ref.endswith("website_directory.directory_sidebar")
                        for ref in refs
                    ),
                    f"{term!r} is not attached to directory_sidebar: {refs}",
                )
        for term in RESULT_TERMS:
            matching = [refs for msgid, refs in entries if msgid == term]
            self.assertTrue(matching, f"no es.po entry for {term!r}")
            self.assertTrue(
                any(
                    ref.endswith("website_directory.directory_results")
                    for ref in matching[0]
                ),
                f"{term!r} is not attached to directory_results: {matching[0]}",
            )
        matching = [refs for msgid, refs in entries if msgid == REMOVE_TERM]
        self.assertTrue(matching, f"no es.po entry for {REMOVE_TERM!r}")
        self.assertTrue(
            any(
                ref.endswith("website_directory.directory_filter_chip")
                for ref in matching[0]
            ),
            f"{REMOVE_TERM!r} is not attached to directory_filter_chip: {matching[0]}",
        )

    def test_sidebar_arch_is_spanish(self):
        """Loading es.po attaches the Spanish terms to the live sidebar record."""
        lang = self.env["res.lang"]._activate_lang("es_ES")
        self.assertTrue(lang)
        module = self.env["ir.module.module"].search(
            [("name", "=", "website_directory")]
        )
        module._update_translations(filter_lang="es_ES", overwrite=True)
        sidebar = self.env.ref("website_directory.directory_sidebar").with_context(
            lang="es_ES"
        )
        arch = sidebar.arch
        for expected in (
            "Zona Comercial",
            "Subcategoría",
            "Todas las zonas",
            "Categoría",
        ):
            self.assertIn(expected, arch)
        self.assertNotIn(">Commercial Zone<", arch)
        self.assertNotIn("All zones", arch)
        # The shared chip's accessible name is a static text node, so it
        # travels the same path as the sidebar's own terms.
        chip = self.env.ref("website_directory.directory_filter_chip").with_context(
            lang="es_ES"
        )
        self.assertIn(REMOVE_TERM_ES, chip.arch)
        self.assertNotIn("Remove filter", chip.arch)
        results = self.env.ref("website_directory.directory_results").with_context(
            lang="es_ES"
        )
        self.assertIn("No se encontraron comercios", results.arch)
        self.assertNotIn(">No businesses found<", results.arch)
        # The result terms are English source: the 7-language setup can
        # translate them; a Spanish literal in the template could not be.
        self.assertIn(
            ">No businesses found<",
            self.env.ref("website_directory.directory_results").arch,
        )
        # Rendering the sidebar the way the controller does yields Spanish.
        html = (
            self.env["ir.qweb"]
            .with_context(lang="es_ES")
            ._render(
                "website_directory.directory_sidebar",
                {
                    "current_zone": "canarias",
                    "zone_options": [("canarias", "Canarias")],
                    "zone_urls": {"canarias": "/comercio"},
                    "zone_clear_url": "/comercio",
                    "category_clear_url": "/comercio",
                    "base_url": "/comercio",
                    "search": "",
                    "category_tree": [],
                    "selected_category": None,
                    "selected_category_path": [None, None, None],
                    "selected_category_json": "[null, null, null]",
                },
            )
        )
        html = re.sub(r"\s+", " ", str(html))
        self.assertIn("Zona Comercial", html)
        self.assertIn("Todas las zonas", html)
        self.assertNotIn("Commercial Zone", html)

    def test_the_chip_announces_itself_in_spanish(self):
        """The words a screen reader reads out, in the rendered page.

        The arch assertions above prove the term reached the record; this
        one proves it survives rendering. Both are needed: an accessible
        name built from an expression attribute translates in neither
        place, and that regression is invisible on screen.
        """
        self.env["res.lang"]._activate_lang("es_ES")
        module = self.env["ir.module.module"].search(
            [("name", "=", "website_directory")]
        )
        module._update_translations(filter_lang="es_ES", overwrite=True)
        html = str(
            self.env["ir.qweb"]
            .with_context(lang="es_ES")
            ._render(
                "website_directory.directory_sidebar",
                {
                    # A zone that is not "canarias" is what draws a chip.
                    "current_zone": "guanarteme",
                    "zone_options": [
                        ("canarias", "Canarias"),
                        ("guanarteme", "Guanarteme"),
                    ],
                    "zone_urls": {"canarias": "/comercio"},
                    "zone_clear_url": "/comercio",
                    "category_clear_url": "/comercio",
                    "base_url": "/comercio",
                    "search": "",
                    "category_tree": [],
                    "selected_category": None,
                    "selected_category_path": [None, None, None],
                    "selected_category_json": "[null, null, null]",
                },
            )
        )
        self.assertIn("wd-filter-remove", html, "no chip rendered to check")
        self.assertIn(REMOVE_TERM_ES, re.sub(r"\s+", " ", html))
        self.assertNotIn("Remove filter", html)
