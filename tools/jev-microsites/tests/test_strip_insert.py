"""Separador.insert: the strip-2 section is inserted before the form, or after
the last existing block when the page has no form."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jev_apply_lib as lib  # noqa: E402

HERO = '<section data-snippet="s_cover" data-name="Hero" style="x">\n    <h1>Hi</h1>\n</section>'
ACERCA = '<section data-snippet="s_attributes_vertical" data-name="Acerca">\n    <p>About</p>\n</section>'
FORM = '<section data-snippet="s_website_form" data-name="Formulario">\n    <form/>\n</section>'
SUBV = '<section data-snippet="s_picture" data-name="Subvenciones">\n    <img/>\n</section>'


def page(*blocks: str) -> str:
    return "<div>\n" + "\n".join("    " + b.replace("\n", "\n    ") for b in blocks) + "\n</div>"


def names(arch: str) -> list[str]:
    return re.findall(r'data-name="([^"]+)"', arch)


class StripInsertTests(unittest.TestCase):
    def test_inserted_before_form_with_indent(self):
        out = lib.insert_separador_before_form(page(HERO, ACERCA, FORM, SUBV), "Consume Productos Canarios")
        self.assertEqual(names(out), ["Hero", "Acerca", "Separador", "Formulario", "Subvenciones"])
        self.assertEqual(lib.extract_section_h2(out, "Separador"), "Consume Productos Canarios")
        line = [l for l in out.splitlines() if 'data-name="Separador"' in l][0]
        self.assertTrue(line.startswith("    <section"))

    def test_without_form_goes_after_last_block(self):
        self.assertEqual(names(lib.insert_separador_before_form(page(HERO, ACERCA), "T")), ["Hero", "Acerca", "Separador"])
        self.assertEqual(names(lib.insert_separador_before_form(page(HERO), "T")), ["Hero", "Separador"])

    def test_text_is_escaped_and_bg_can_follow(self):
        out = lib.insert_separador_before_form(page(HERO, FORM), "Pan & vino")
        self.assertIn("Pan &amp; vino", out)
        url = "/web/image/res.company/7/microsite_banner_image"
        out = lib.set_section_background(out, "Separador", url)
        self.assertEqual(lib.extract_section_bg(out, "Separador"), url)

    def test_refuses_duplicate_and_missing_anchor(self):
        once = lib.insert_separador_before_form(page(HERO, FORM), "x")
        with self.assertRaises(lib.ArchError):
            lib.insert_separador_before_form(once, "y")
        with self.assertRaises(lib.SectionNotFound):
            lib.insert_separador_before_form("<div/>", "x")

    def test_parse_campo_accepts_separador_insert(self):
        target = lib.parse_campo("ir_ui_view.12.Separador.insert")
        self.assertEqual((target.kind, target.section), (lib.KIND_VIEW_INSERT, "Separador"))


if __name__ == "__main__":
    unittest.main()
