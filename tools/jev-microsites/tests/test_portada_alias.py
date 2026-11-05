"""Insert anchors accept the cover under either name: ``Hero`` (builder) or
``Portada`` (legacy ``s_adventure`` homepages such as views 4911, 4927, 4943
and 4951)."""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jev_apply_lib as lib  # noqa: E402

PORTADA = ('<section class="s_adventure o_colored_level" data-snippet="s_adventure" data-name="Portada">\n'
           '    <h1>Maquifer</h1>\n</section>')
HERO = '<section data-snippet="s_cover" data-name="Hero">\n    <h1>Hi</h1>\n</section>'
FORM = '<section data-snippet="s_website_form" data-name="Formulario">\n    <form/>\n</section>'
SUBV = '<section data-snippet="s_picture" data-name="Subvenciones">\n    <img/>\n</section>'
PAYLOAD = {"about_title": "Nuestra historia", "about": "Cooperativa canaria.",
           "services_title": "Nuestro servicio", "services": "Herramientas.", "slug": "maquifercoop"}


def page(*blocks: str) -> str:
    return "<div>\n" + "\n".join("    " + b.replace("\n", "\n    ") for b in blocks) + "\n</div>"


def names(arch: str) -> list[str]:
    return re.findall(r'data-name="([^"]+)"', arch)


class HeroSectionHelperTests(unittest.TestCase):
    def test_either_name_first_in_document_order(self):
        self.assertEqual(lib._hero_section(page(PORTADA, FORM)).name, "Portada")
        self.assertEqual(lib._hero_section(page(HERO, FORM)).name, "Hero")
        self.assertEqual(lib._hero_section(page(PORTADA, HERO)).name, "Portada")
        self.assertEqual(lib._hero_section(page(HERO, PORTADA)).name, "Hero")
        self.assertIsNone(lib._hero_section(page(FORM)))
        self.assertEqual(lib.HERO_NAMES, ("Hero", "Portada"))

    def test_require_raises_section_not_found(self):
        with self.assertRaises(lib.SectionNotFound):
            lib._require_hero_section(page(FORM))


class PortadaSec1InsertTests(unittest.TestCase):
    def test_sec1_inserted_right_after_portada_with_indent(self):
        arch = page(PORTADA, FORM)
        out = lib.insert_sec1_after_hero(arch, "Ferretería & suministros")
        self.assertEqual(names(out), ["Portada", "SEC1", "Formulario"])
        portada, sec1 = lib.find_section(out, "Portada"), lib.find_section(out, "SEC1")
        self.assertEqual(out[portada.end:sec1.start], "\n    ")
        self.assertEqual(out[:portada.end], arch[:portada.end])
        self.assertTrue(out.endswith(arch[portada.end:]))
        self.assertEqual(lib.extract_section_h2(out, "SEC1"), "Ferretería & suministros")

    def test_duplicate_still_refused(self):
        once = lib.insert_sec1_after_hero(page(PORTADA), "x")
        with self.assertRaises(lib.ArchError):
            lib.insert_sec1_after_hero(once, "y")


class PortadaAcercaInsertTests(unittest.TestCase):
    def test_acerca_after_portada_without_sec1(self):
        arch = page(PORTADA, FORM)
        out = lib.insert_acerca_section(arch, PAYLOAD)
        self.assertEqual(names(out)[:3], ["Portada", "Acerca", "Column"])
        portada, acerca = lib.find_section(out, "Portada"), lib.find_section(out, "Acerca")
        self.assertEqual(out[portada.end:acerca.start], "\n    ")
        self.assertTrue(out.endswith(arch[portada.end:]))
        self.assertEqual(lib.acerca_anchor_name(arch), "Portada")
        self.assertIsNone(lib.acerca_anchor_name(page(FORM)))

    def test_sec1_then_acerca_keeps_order_rule(self):
        # Same run as the maquifercoop CSV: SEC1.insert first, Acerca.insert
        # anchors after the SEC1 just inserted, not after the cover.
        arch = page(PORTADA, FORM)
        out = lib.insert_sec1_after_hero(arch, "Intro")
        self.assertEqual(lib.acerca_anchor_name(out), "SEC1")
        out = lib.insert_acerca_section(out, PAYLOAD)
        self.assertEqual([n for n in names(out) if n != "Column"], ["Portada", "SEC1", "Acerca", "Formulario"])
        self.assertEqual(lib.extract_acerca_section(out),
                         lib.acerca_payload_key(lib.parse_acerca_payload(json.dumps(PAYLOAD))))


class PortadaSeparadorInsertTests(unittest.TestCase):
    def test_before_form_regardless_of_cover_name(self):
        out = lib.insert_separador_before_form(page(PORTADA, FORM, SUBV), "Consume Productos Canarios")
        self.assertEqual(names(out), ["Portada", "Separador", "Formulario", "Subvenciones"])

    def test_without_form_goes_after_portada_or_later_block(self):
        self.assertEqual(names(lib.insert_separador_before_form(page(PORTADA), "T")), ["Portada", "Separador"])
        with_sec1 = lib.insert_sec1_after_hero(page(PORTADA), "Intro")
        self.assertEqual(names(lib.insert_separador_before_form(with_sec1, "T")), ["Portada", "SEC1", "Separador"])
        with self.assertRaises(lib.SectionNotFound):
            lib.insert_separador_before_form(page(SUBV), "T")


if __name__ == "__main__":
    unittest.main()
