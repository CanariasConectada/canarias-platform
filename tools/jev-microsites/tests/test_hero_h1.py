"""<Section>.h1: read and replace the Hero headline, keeping its <span> wrapper."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jev_apply_lib as lib  # noqa: E402

HERO = ('<section data-snippet="s_cover" data-name="Hero" style="x">\n'
        '    <h1 class="display-4-fs" style="y">\n        <span class="display-4-fs">MARIO &amp; HIJOS</span>\n    </h1>\n'
        '    <p>sub</p>\n</section>')
PLAIN = '<section data-name="Portada">\n    <h1>Old</h1>\n    <section data-name="Inner"><h1>Nested</h1></section>\n</section>'


class HeroHeadlineTests(unittest.TestCase):
    def test_extract_strips_span_and_unescapes(self):
        self.assertEqual(lib.extract_section_h1(HERO, "Hero"), "MARIO & HIJOS")

    def test_replace_keeps_span_and_everything_else(self):
        out = lib.replace_section_h1(HERO, "Hero", "24 Horas Savage")
        self.assertIn('<span class="display-4-fs">24 Horas Savage</span>', out)
        self.assertEqual(out.replace("24 Horas Savage", "MARIO &amp; HIJOS"), HERO)
        self.assertEqual(lib.extract_section_h1(out, "Hero"), "24 Horas Savage")

    def test_plain_h1_and_nested_section_ignored(self):
        out = lib.replace_section_h1(PLAIN, "Portada", "New & co")
        self.assertIn("<h1>New &amp; co</h1>", out)
        self.assertIn("<h1>Nested</h1>", out)

    def test_missing_h1_raises_and_none_on_extract(self):
        arch = '<section data-name="Hero"><p>x</p></section>'
        self.assertIsNone(lib.extract_section_h1(arch, "Hero"))
        with self.assertRaises(lib.ArchError):
            lib.replace_section_h1(arch, "Hero", "x")

    def test_parse_campo_h1(self):
        t = lib.parse_campo("ir_ui_view.9.Hero.h1")
        self.assertEqual((t.kind, t.section, t.view_id), (lib.KIND_VIEW_H1, "Hero", 9))


if __name__ == "__main__":
    unittest.main()
