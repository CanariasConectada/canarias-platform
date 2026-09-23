"""Tests for jev_apply_lib, revertir and aplicar (no network, no DB).

Run from the tool directory::

    python3 -m unittest

or from the repository root::

    python3 -m unittest discover -s tools/jev-microsites/tests -t tools/jev-microsites
"""
from __future__ import annotations

import base64
import contextlib
import csv
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOL_DIR = Path(__file__).resolve().parents[1]
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

import aplicar  # noqa: E402
import jev_apply_lib as lib  # noqa: E402
import revertir  # noqa: E402

HERO_STYLE = ("background-image: url('/web/image/ir.attachment/4773/datas'); background-size: cover; "
              "background-position: center; background-attachment: fixed; min-height: 600px;")

ARCH = f'''<div id="wrap">
    <section class="s_cover parallax s_parallax_is_fixed o_cc o_cc5" data-name="Hero" data-snippet="s_cover" style="{HERO_STYLE}">
        <div class="container">
            <h1 class="display-3">Little Beach</h1>
            <h2 class="h4-fs">Bienvenidos a nuestro espacio</h2>
        </div>
    </section>
    <section class="s_text_block pt40 pb40 o_colored_level" data-name="Acerca" data-snippet="s_text_block">
        <div class="container">
            <div class="row">
                <div class="col-lg-6">
                    <h2>Sobre nosotros</h2>
                    <p>Texto &amp; m&aacute;s <b>negrita</b></p>
                </div>
                <div class="col-lg-6">
                    <div class="card card-body">Otra caja</div>
                </div>
            </div>
        </div>
    </section>
    <section class="s_showcase" data-name="Servicios" data-snippet="s_showcase">
        <div class="container">
            <section class="s_inner" data-name="Inner">
                <h2>Inner heading</h2>
            </section>
            <h2>Outer heading</h2>
        </div>
    </section>
    <section class="s_call_to_action" data-name="Separador" data-snippet="s_call_to_action">
        <div class="container"><h2>Ll&aacute;manos</h2></div>
    </section>
    <section class="s_x" data-name="ConEstilo" style="min-height: 400px;">
        <div class="container"><h2>Estilo</h2></div>
    </section>
</div>
'''

URL_68_HERO = "/web/image/res.company/68/microsite_hero_image"


# ---------------------------------------------------------------------------
# Arch helpers
# ---------------------------------------------------------------------------

class FindSectionTests(unittest.TestCase):
    def test_depth_aware_close(self):
        sec = lib.find_section(ARCH, "Servicios")
        self.assertIsNotNone(sec)
        text = sec.group(0)
        self.assertTrue(text.startswith('<section class="s_showcase"'))
        self.assertIn("Outer heading", text)
        self.assertIn("Inner heading", text)
        self.assertTrue(text.endswith("</section>"))
        # The outer close is the one after "Outer heading", not the inner one.
        self.assertEqual(text.count("</section>"), 2)
        self.assertLess(text.index("Outer heading"), text.rindex("</section>"))

    def test_nested_section_found_on_its_own(self):
        inner = lib.find_section(ARCH, "Inner")
        self.assertEqual(inner.group(0).count("</section>"), 1)
        self.assertIn("Inner heading", inner.body)
        self.assertNotIn("Outer heading", inner.body)

    def test_missing_and_unclosed(self):
        self.assertIsNone(lib.find_section(ARCH, "Nope"))
        broken = '<section data-name="Hero"><div><section data-name="X"></section>'
        with self.assertRaises(lib.ArchError):
            lib.find_section(broken, "Hero")

    def test_attribute_must_be_data_name(self):
        arch = '<section data-other-name="Hero"></section><section data-name="Hero"></section>'
        sec = lib.find_section(arch, "Hero")
        self.assertEqual(sec.start, arch.index('<section data-name="Hero"'))


class H2Tests(unittest.TestCase):
    def test_extract(self):
        self.assertEqual(lib.extract_section_h2(ARCH, "Hero"), "Bienvenidos a nuestro espacio")
        self.assertEqual(lib.extract_section_h2(ARCH, "Acerca"), "Sobre nosotros")
        self.assertEqual(lib.extract_section_h2(ARCH, "Separador"), "Llámanos")
        self.assertEqual(lib.extract_section_h2(ARCH, "Servicios"), "Outer heading")
        self.assertEqual(lib.extract_section_h2(ARCH, "Inner"), "Inner heading")
        with self.assertRaises(lib.SectionNotFound):
            lib.extract_section_h2(ARCH, "Nope")

    def test_no_h2(self):
        arch = '<section data-name="Hero"><h1>x</h1></section>'
        self.assertIsNone(lib.extract_section_h2(arch, "Hero"))
        with self.assertRaises(lib.ArchError):
            lib.replace_section_h2(arch, "Hero", "y")

    def test_replace_escapes_and_keeps_rest(self):
        out = lib.replace_section_h2(ARCH, "Acerca", "Tom & Jerry <3")
        self.assertIn("<h2>Tom &amp; Jerry &lt;3</h2>", out)
        self.assertEqual(lib.extract_section_h2(out, "Acerca"), "Tom & Jerry <3")
        before = ARCH.index("<h2>Sobre nosotros</h2>") + len("<h2>")
        after = before + len("Sobre nosotros")
        self.assertEqual(out[:before], ARCH[:before])
        self.assertEqual(out[before + len("Tom &amp; Jerry &lt;3"):], ARCH[after:])

    def test_replace_skips_nested_section_h2(self):
        out = lib.replace_section_h2(ARCH, "Servicios", "Nuevo")
        self.assertIn("<h2>Inner heading</h2>", out)
        self.assertIn("<h2>Nuevo</h2>", out)
        self.assertNotIn("Outer heading", out)


class BackgroundTests(unittest.TestCase):
    def test_extract(self):
        self.assertEqual(lib.extract_section_bg(ARCH, "Hero"), "/web/image/ir.attachment/4773/datas")
        self.assertIsNone(lib.extract_section_bg(ARCH, "Acerca"))
        self.assertIsNone(lib.extract_section_bg(ARCH, "ConEstilo"))

    def _assert_only_open_tag_changed(self, name, out):
        old, new = lib.find_section(ARCH, name), lib.find_section(out, name)
        self.assertEqual(out[:old.start], ARCH[:old.start])
        self.assertEqual(out[new.open_end:], ARCH[old.open_end:])

    def test_replace_existing_url(self):
        out = lib.set_section_background(ARCH, "Hero", URL_68_HERO)
        self.assertEqual(lib.extract_section_bg(out, "Hero"), URL_68_HERO)
        self.assertNotIn("4773", out)
        self.assertIn(f"style=\"background-image: url('{URL_68_HERO}'); background-size: cover; "
                      "background-position: center; background-attachment: fixed; min-height: 600px;\"", out)
        self._assert_only_open_tag_changed("Hero", out)

    def test_prepend_to_existing_style(self):
        out = lib.set_section_background(ARCH, "ConEstilo", URL_68_HERO)
        self.assertIn(f"style=\"background-image: url('{URL_68_HERO}'); background-size: cover; "
                      "background-position: center; background-attachment: fixed; min-height: 400px;\"", out)
        self._assert_only_open_tag_changed("ConEstilo", out)

    def test_create_style(self):
        out = lib.set_section_background(ARCH, "Separador", URL_68_HERO)
        self.assertIn('data-snippet="s_call_to_action" style="background-image: url(\''
                      + URL_68_HERO + "'); background-size: cover; background-position: center; "
                      "background-attachment: fixed;\">", out)
        self.assertEqual(lib.extract_section_bg(out, "Separador"), URL_68_HERO)
        self._assert_only_open_tag_changed("Separador", out)

    def test_gradient_declaration_is_replaced_not_shadowed(self):
        arch = lib.insert_sec1_after_hero(ARCH, "Hola")
        out = lib.set_section_background(arch, "SEC1", "/web/image/res.company/68/microsite_intro_image")
        sec = lib.find_section(out, "SEC1")
        self.assertNotIn("linear-gradient", sec.open_tag)
        self.assertEqual(sec.open_tag.count("background-image"), 1)
        self.assertEqual(lib.extract_section_bg(out, "SEC1"), "/web/image/res.company/68/microsite_intro_image")

    def test_url_whitelist(self):
        self.assertEqual(lib.check_bg_url(URL_68_HERO, 68), "")
        self.assertEqual(lib.check_bg_url(URL_68_HERO, None), "")
        self.assertIn("does not belong to company 69", lib.check_bg_url(URL_68_HERO, 69))
        for bad in ("/web/image/res.company/68/logo", "/web/image/ir.attachment/4773/datas",
                    "javascript:alert(1)", URL_68_HERO + "');color:red;x=('",
                    "http://evil/web/image/res.company/68/microsite_hero_image", "", URL_68_HERO + "?x=1"):
            self.assertTrue(lib.check_bg_url(bad, 68), bad)
            with self.assertRaises(lib.ArchError, msg=bad):
                lib.set_section_background(ARCH, "Hero", bad)
        self.assertEqual(lib.bg_url_field(URL_68_HERO), "microsite_hero_image")


class InsertSec1Tests(unittest.TestCase):
    def test_insert_after_hero(self):
        out = lib.insert_sec1_after_hero(ARCH, "Bienvenidos & más")
        hero = lib.find_section(out, "Hero")
        sec1 = lib.find_section(out, "SEC1")
        self.assertEqual(out[hero.end:sec1.start], "\n    ")
        self.assertEqual(lib.extract_section_h2(out, "SEC1"), "Bienvenidos & más")
        self.assertIn("<h2 class=\"h3-fs text-center text-white\">Bienvenidos &amp; más</h2>", out)
        self.assertTrue(out.endswith(ARCH[hero.end:]))
        self.assertEqual(out[:hero.end], ARCH[:hero.end])
        self.assertLess(sec1.end, lib.find_section(out, "Acerca").start)

    def test_refuses_when_present(self):
        once = lib.insert_sec1_after_hero(ARCH, "x")
        with self.assertRaises(lib.ArchError):
            lib.insert_sec1_after_hero(once, "y")

    def test_needs_hero(self):
        with self.assertRaises(lib.SectionNotFound):
            lib.insert_sec1_after_hero('<section data-name="Acerca"></section>', "x")


# ---------------------------------------------------------------------------
# Legacy "Acerca" block
# ---------------------------------------------------------------------------

def _legacy_column(icon, title, preview, full, col_id):
    return (f"""            <div class="border o_colored_level col-lg-6 text-center pt-4 pb-4" data-name="Column">
            <span class="fa {icon} fa-3x mb-3" style="display: block;"/>
            <h6 class="text-center">{title}</h6>
            <small class="text-muted d-block" style="padding: 0 20px;">{preview}</small>
            <div class="mt-3 text-center">
                <a href="#{col_id}" data-bs-toggle="collapse" class="btn btn-primary rounded-pill px-4">Leer más</a>
            </div>
            <div id="{col_id}" class="collapse mt-3">
                <div class="card card-body bg-light">{full}</div>
            </div>
        </div>""")


COL1 = _legacy_column("fa-book", "Nuestra historia", "Historia corta", "Historia completa",
                      "acerca1_lapapayafitnesscenter")
COL2 = _legacy_column("fa-cogs", "Nuestros servicios", "Servicios cortos", "Servicios completos",
                      "acerca2_lapapayafitnesscenter")


def _legacy_arch(columns, sec1=True):
    sec1_block = ('    <section class="s_kickoff" data-name="SEC1"><div class="container">'
                  '<h2>Intro</h2></div></section>\n') if sec1 else ""
    return (
        '<div id="wrap">\n'
        '    <section class="s_cover" data-name="Hero"><div class="container"><h2>Hola</h2></div></section>\n'
        + sec1_block +
        '    <section class="s_attributes_vertical o_colored_level pt48 pb56" '
        'data-snippet="s_attributes_vertical" data-name="Acerca">\n'
        '        <div class="container">\n'
        '            <div class="row justify-content-center">\n'
        + columns + '\n'
        '        </div>\n'
        '    </div>\n'
        '</section>\n'
        '    <section class="s_footer" data-name="Contacto"><div><h2>Contacto</h2></div></section>\n'
        '</div>\n')


LEGACY_TWO = _legacy_arch(COL1 + "\n" + COL2)
LEGACY_ONE = _legacy_arch(COL1)
LEGACY_BACK_TO_BACK = _legacy_arch(COL1 + COL2.lstrip())   # "</div><div class="border ..."
NO_ACERCA = LEGACY_TWO[:LEGACY_TWO.index('    <section class="s_attributes_vertical')] \
    + LEGACY_TWO[LEGACY_TWO.index('    <section class="s_footer"'):]
NO_ACERCA_NO_SEC1 = NO_ACERCA.replace(
    '    <section class="s_kickoff" data-name="SEC1"><div class="container"><h2>Intro</h2></div></section>\n', "")

PAYLOAD = {"about_title": "Sobre nosotros", "about": "Somos & <b>fuertes</b>",
           "services_title": "Nuestros servicios", "services": "Entrenamiento " * 20, "slug": "lapapaya"}


class AcercaColumnTests(unittest.TestCase):
    def test_columns_found_depth_aware(self):
        for arch in (LEGACY_TWO, LEGACY_BACK_TO_BACK):
            cols = lib.acerca_columns(arch)
            self.assertEqual(len(cols), 2)
            self.assertIn("Historia completa", arch[cols[0].start:cols[0].end])
            self.assertNotIn("Servicios", arch[cols[0].start:cols[0].end])
            self.assertIn("Servicios completos", arch[cols[1].start:cols[1].end])
        self.assertIn('</div><div class="border', LEGACY_BACK_TO_BACK)

    def test_extract(self):
        self.assertEqual(lib.extract_acerca_column(LEGACY_TWO, 1), "Historia completa")
        self.assertEqual(lib.extract_acerca_column(LEGACY_TWO, 2), "Servicios completos")
        self.assertEqual(lib.extract_acerca_column(LEGACY_ONE, 2), "")
        with self.assertRaises(lib.SectionNotFound):
            lib.extract_acerca_column(NO_ACERCA, 1)

    def test_replace_escapes_and_keeps_rest(self):
        text = "Tom & Jerry <3 desde 1990"
        out = lib.set_acerca_column(LEGACY_TWO, 2, text)
        esc = "Tom &amp; Jerry &lt;3 desde 1990"
        a_start = LEGACY_TWO.index("Servicios cortos")
        a_end = a_start + len("Servicios cortos")
        b_start = LEGACY_TWO.index("Servicios completos")
        b_end = b_start + len("Servicios completos")
        expected = (LEGACY_TWO[:a_start] + esc + LEGACY_TWO[a_end:b_start] + esc + LEGACY_TWO[b_end:])
        self.assertEqual(out, expected)
        self.assertEqual(lib.extract_acerca_column(out, 2), text)
        self.assertEqual(lib.extract_acerca_column(out, 1), "Historia completa")
        # back to back columns edit the right column too
        out = lib.set_acerca_column(LEGACY_BACK_TO_BACK, 1, "Nueva")
        self.assertEqual(lib.extract_acerca_column(out, 1), "Nueva")
        self.assertEqual(lib.extract_acerca_column(out, 2), "Servicios completos")
        self.assertEqual(out, LEGACY_BACK_TO_BACK.replace("Historia corta", "Nueva")
                         .replace("Historia completa", "Nueva"))

    def test_preview_truncation(self):
        self.assertEqual(lib.acerca_preview("a" * 120), "a" * 120)
        self.assertEqual(lib.acerca_preview("a" * 121), "a" * 120 + "...")
        out = lib.set_acerca_column(LEGACY_TWO, 1, "b" * 121)
        self.assertIn(f'style="padding: 0 20px;">{"b" * 120}...</small>', out)
        self.assertIn(f'bg-light">{"b" * 121}</div>', out)
        out = lib.set_acerca_column(LEGACY_TWO, 1, "c" * 120)
        self.assertIn(f'style="padding: 0 20px;">{"c" * 120}</small>', out)
        self.assertNotIn("c...", out)

    def test_missing_column_appended(self):
        out = lib.set_acerca_column(LEGACY_ONE, 2, "Servicios & más", site_id=42)
        cols = lib.acerca_columns(out)
        self.assertEqual(len(cols), 2)
        self.assertEqual(out[:cols[0].end], LEGACY_ONE[:cols[0].end])
        self.assertEqual(out[cols[1].end:], LEGACY_ONE[cols[0].end:])
        col2 = out[cols[0].end:cols[1].end]
        self.assertTrue(col2.startswith("\n            <div class=\"border"))
        self.assertIn('class="fa fa-cogs fa-3x mb-3"', col2)
        self.assertIn('<h6 class="text-center">Nuestros servicios</h6>', col2)
        self.assertIn('href="#acerca2_lapapayafitnesscenter"', col2)
        self.assertIn('<div id="acerca2_lapapayafitnesscenter" class="collapse mt-3">', col2)
        self.assertIn(">Servicios &amp; más</small>", col2)
        self.assertEqual(lib.extract_acerca_column(out, 2), "Servicios & más")
        # slug fallback when the section carries no acerca id
        bare = LEGACY_ONE.replace("acerca1_lapapayafitnesscenter", "other")
        out = lib.set_acerca_column(bare, 2, "x", site_id=42)
        self.assertIn('id="acerca2_site42"', out)
        with self.assertRaises(lib.ArchError):
            lib.set_acerca_column(LEGACY_TWO, 1, "  ")

    def test_columns_identified_by_id_not_position(self):
        arch = _legacy_arch(COL2)   # only the services column (acerca2_, fa-cogs)
        self.assertEqual(lib.extract_acerca_column(arch, 1), "")
        self.assertEqual(lib.extract_acerca_column(arch, 2), "Servicios completos")
        self.assertEqual(list(lib.acerca_column_slots(arch)), [2])

        out = lib.set_acerca_column(arch, 1, "Historia & nueva", site_id=42)
        slots = lib.acerca_column_slots(out)
        self.assertEqual(sorted(slots), [1, 2])
        self.assertLess(slots[1].end, slots[2].start)      # about before services
        col2 = arch[lib.acerca_column_slots(arch)[2].start:lib.acerca_column_slots(arch)[2].end]
        self.assertEqual(out[slots[2].start:slots[2].end], col2)   # byte-identical
        self.assertEqual(out[slots[2].start:], arch[lib.acerca_column_slots(arch)[2].start:])
        new_col = out[slots[1].start:slots[1].end]
        self.assertIn('class="fa fa-book fa-3x mb-3"', new_col)
        self.assertIn('id="acerca1_lapapayafitnesscenter"', new_col)
        self.assertEqual(lib.extract_acerca_column(out, 1), "Historia & nueva")
        self.assertEqual(lib.extract_acerca_column(out, 2), "Servicios completos")

        out = lib.set_acerca_column(arch, 2, "Otros servicios")
        self.assertEqual(out, arch.replace("Servicios cortos", "Otros servicios")
                         .replace("Servicios completos", "Otros servicios"))
        self.assertEqual(lib.extract_acerca_column(out, 1), "")

        # document order does not matter: col2 first, col1 second
        swapped = _legacy_arch(COL2 + "\n" + COL1)
        self.assertEqual(lib.extract_acerca_column(swapped, 1), "Historia completa")
        out = lib.set_acerca_column(swapped, 1, "Nueva")
        self.assertEqual(out, swapped.replace("Historia corta", "Nueva").replace("Historia completa", "Nueva"))

        # positional fallback only when no column carries an acerca id
        bare = _legacy_arch(COL1.replace("acerca1_", "x1_") + "\n" + COL2.replace("acerca2_", "x2_"))
        self.assertEqual(lib.extract_acerca_column(bare, 1), "Historia completa")
        self.assertEqual(lib.extract_acerca_column(bare, 2), "Servicios completos")
        mixed = _legacy_arch(COL1.replace("acerca1_", "x1_") + "\n" + COL2)
        self.assertEqual(lib.extract_acerca_column(mixed, 1), "")
        self.assertEqual(lib.extract_acerca_column(mixed, 2), "Servicios completos")

    def test_duplicate_slot_raises(self):
        arch = _legacy_arch(COL1 + "\n" + COL2.replace("acerca2_", "acerca1_"))
        for call in (lambda: lib.extract_acerca_column(arch, 1),
                     lambda: lib.set_acerca_column(arch, 2, "x"),
                     lambda: lib.extract_acerca_section(arch)):
            with self.assertRaises(lib.ArchError):
                call()

    def test_zero_columns(self):
        empty = _legacy_arch("")
        self.assertEqual(lib.acerca_columns(empty), [])
        self.assertEqual(lib.extract_acerca_column(empty, 1), "")
        out = lib.set_acerca_column(empty, 1, "Historia", site_id=42)
        self.assertEqual(sorted(lib.acerca_column_slots(out)), [1])
        self.assertIn('id="acerca1_site42"', out)
        self.assertEqual(lib.extract_acerca_column(out, 1), "Historia")
        self.assertIn('\n                <div class="border', out)   # row indent + 4
        self.assertIsNotNone(lib.find_section(out, "Contacto"))
        out2 = lib.set_acerca_column(out, 2, "Servicios")
        slots = lib.acerca_column_slots(out2)
        self.assertLess(slots[1].end, slots[2].start)
        self.assertIn('id="acerca2_site42"', out2)
        # col2 alone into an empty section, then col1 goes before it
        out = lib.set_acerca_column(lib.set_acerca_column(empty, 2, "S", site_id=7), 1, "H", site_id=7)
        slots = lib.acerca_column_slots(out)
        self.assertLess(slots[1].end, slots[2].start)
        self.assertEqual((lib.extract_acerca_column(out, 1), lib.extract_acerca_column(out, 2)), ("H", "S"))

    def test_back_to_back_append(self):
        arch = _legacy_arch(COL1 + '<div class="x">keep</div>')
        out = lib.set_acerca_column(arch, 2, "Nuevo", site_id=1)
        self.assertEqual(lib.extract_acerca_column(out, 2), "Nuevo")
        self.assertLess(out.index("acerca2_"), out.index('<div class="x">keep</div>'))


class AcercaInsertTests(unittest.TestCase):
    def test_insert_after_sec1(self):
        out = lib.insert_acerca_section(NO_ACERCA, PAYLOAD)
        sec1, acerca = lib.find_section(out, "SEC1"), lib.find_section(out, "Acerca")
        self.assertEqual(out[sec1.end:acerca.start], "\n    ")
        self.assertEqual(out[:sec1.end], NO_ACERCA[:sec1.end])
        self.assertEqual(out[acerca.end:], NO_ACERCA[sec1.end:])
        self.assertEqual(lib.extract_acerca_column(out, 1), PAYLOAD["about"])
        self.assertEqual(lib.extract_acerca_column(out, 2), PAYLOAD["services"].strip())
        self.assertIn('id="acerca1_lapapaya"', out)
        self.assertIn('id="acerca2_lapapaya"', out)
        self.assertIn('class="fa fa-cogs fa-3x mb-3"', out)
        self.assertIn(">Somos &amp; &lt;b&gt;fuertes&lt;/b&gt;</small>", out)
        self.assertIn(">" + PAYLOAD["services"][:120] + "...</small>", out)
        self.assertEqual(out.count('data-name="Column"'), 2)
        self.assertEqual(lib.extract_acerca_section(out),
                         lib.acerca_payload_key(lib.parse_acerca_payload(json.dumps(PAYLOAD))))
        self.assertEqual(lib.extract_acerca_section(NO_ACERCA), "")

    def test_insert_after_hero_without_sec1(self):
        out = lib.insert_acerca_section(NO_ACERCA_NO_SEC1, PAYLOAD)
        hero, acerca = lib.find_section(out, "Hero"), lib.find_section(out, "Acerca")
        self.assertEqual(out[hero.end:acerca.start], "\n    ")
        self.assertTrue(out.endswith(NO_ACERCA_NO_SEC1[hero.end:]))

    def test_refuses_when_present(self):
        with self.assertRaises(lib.ArchError):
            lib.insert_acerca_section(LEGACY_TWO, PAYLOAD)

    def test_default_titles(self):
        payload = dict(PAYLOAD, about_title="", services_title=" ")
        out = lib.insert_acerca_section(NO_ACERCA, payload)
        self.assertIn('<h6 class="text-center">Sobre nosotros</h6>', out)
        self.assertIn('<h6 class="text-center">Nuestros servicios</h6>', out)
        self.assertEqual(lib.extract_acerca_section(out),
                         lib.acerca_payload_key(lib.parse_acerca_payload(json.dumps(payload))))

    def test_payload_validation(self):
        bad = ["", "not json", "[]", json.dumps({k: v for k, v in PAYLOAD.items() if k != "slug"}),
               json.dumps(dict(PAYLOAD, about="  ")), json.dumps(dict(PAYLOAD, services=3)),
               json.dumps(dict(PAYLOAD, slug='x" onclick="y')), json.dumps(dict(PAYLOAD, extra="x"))]
        for value in bad:
            with self.assertRaises(ValueError, msg=value):
                lib.parse_acerca_payload(value)
        with self.assertRaises(lib.ArchError):
            lib.insert_acerca_section(NO_ACERCA, dict(PAYLOAD, slug=""))


# ---------------------------------------------------------------------------
# campo / zip / csv
# ---------------------------------------------------------------------------

class ParseCampoTests(unittest.TestCase):
    def test_valid(self):
        t = lib.parse_campo("res_company.microsite_intro_title")
        self.assertEqual((t.kind, t.model, t.field), (lib.KIND_COMPANY_FIELD, "res.company", "microsite_intro_title"))
        t = lib.parse_campo("res_company.microsite_hero_image")
        self.assertEqual(t.kind, lib.KIND_COMPANY_IMAGE)
        t = lib.parse_campo("ir_ui_view.3352.Hero.bg")
        self.assertEqual((t.kind, t.view_id, t.section, t.field), (lib.KIND_VIEW_BG, 3352, "Hero", "arch_db"))
        self.assertEqual(lib.parse_campo("ir_ui_view.1.SEC1.h2").kind, lib.KIND_VIEW_H2)
        self.assertEqual(lib.parse_campo(" ir_ui_view.1.SEC1.insert ").kind, lib.KIND_VIEW_INSERT)
        t = lib.parse_campo("ir_ui_view.7.Acerca.col2")
        self.assertEqual((t.kind, t.section, t.column), (lib.KIND_VIEW_COLUMN, "Acerca", 2))
        self.assertEqual(lib.parse_campo("ir_ui_view.7.Acerca.insert").kind, lib.KIND_VIEW_INSERT)
        t = lib.parse_campo("res_company.microsite_about_text")
        self.assertEqual((t.kind, t.field), (lib.KIND_COMPANY_FIELD, "microsite_about_text"))
        self.assertEqual(lib.parse_campo("res_company.microsite_services_text").kind, lib.KIND_COMPANY_FIELD)

    def test_processing_order(self):
        def row(campo, line):
            return lib.Change(68, campo, "", "", 1.0, "", lib.parse_campo(campo), line)
        rows = [row("ir_ui_view.1.Hero.bg", 1), row("ir_ui_view.1.SEC1.h2", 2), row("ir_ui_view.1.Acerca.col1", 3),
                row("ir_ui_view.1.Acerca.insert", 4), row("ir_ui_view.1.SEC1.insert", 5),
                row("res_company.microsite_about_text", 6)]
        ordered = [c.campo for c in lib.group_by_site(rows)[68]]
        self.assertEqual(ordered, ["res_company.microsite_about_text", "ir_ui_view.1.SEC1.insert",
                                   "ir_ui_view.1.Acerca.insert", "ir_ui_view.1.Acerca.col1",
                                   "ir_ui_view.1.SEC1.h2", "ir_ui_view.1.Hero.bg"])

    def test_invalid(self):
        for bad in ("", "foo", "res_company.", "ir_ui_view.x.Hero.bg", "ir_ui_view.1.Hero.insert",
                    "ir_ui_view.1.Hero.style", "res_company.a.b", "ir_ui_view.1.Acerca.col3",
                    "ir_ui_view.1.Hero.col1", "ir_ui_view.1.Acerca.col"):
            with self.assertRaises(lib.CampoError, msg=bad):
                lib.parse_campo(bad)


class ZipContainmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "zip"
        (self.root / "site" / "hero").mkdir(parents=True)
        (self.root / "site" / "hero" / "portada.png").write_bytes(b"png")
        (Path(self.tmp.name) / "outside.png").write_bytes(b"x")

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid(self):
        self.assertEqual(lib.zip_image_path(self.root, "site/hero/portada.png"),
                         (self.root / "site" / "hero" / "portada.png").resolve())

    def test_rejections(self):
        for bad in ("../outside.png", "site/../../outside.png", "/etc/passwd", "", "  ",
                    str(Path(self.tmp.name) / "outside.png"), "site/hero/../../../outside.png"):
            with self.assertRaises(ValueError, msg=bad):
                lib.zip_image_path(self.root, bad)

    def test_symlink_escape(self):
        link = self.root / "site" / "link.png"
        try:
            link.symlink_to(Path(self.tmp.name) / "outside.png")
        except OSError:
            self.skipTest("symlinks not supported")
        with self.assertRaises(ValueError):
            lib.zip_image_path(self.root, "site/link.png")


class LoadChangesTests(unittest.TestCase):
    def test_invalid_rows_are_collected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.csv"
            path.write_text('site,campo,valor_anterior,valor_nuevo,confianza,motivo\n'
                            '68,res_company.microsite_intro_title,a,b,0.9,m\n'
                            'x,res_company.microsite_intro_title,a,b,0.9,m\n'
                            '68,bogus,a,b,0.9,m\n'
                            '68,ir_ui_view.1.Hero.bg,a,b,abc,m\n', encoding="utf-8")
            changes, invalid = lib.load_changes(path)
        self.assertEqual(len(changes), 1)
        self.assertEqual([r.line for r in invalid], [2, 3, 4])


class LanguageOrderTests(unittest.TestCase):
    def test_primary_first_then_sorted(self):
        self.assertEqual(lib.order_languages(["fr_FR", "en_US", "es_ES", "de_DE"], "es_ES"),
                         ["es_ES", "de_DE", "en_US", "fr_FR"])
        self.assertEqual(lib.order_languages(["en_US"], "es_ES"), ["en_US"])


# ---------------------------------------------------------------------------
# Backup file and revertir
# ---------------------------------------------------------------------------

def _rec(event, key=("ir.ui.view", 1, "arch_db", "es_ES"), ts="2026-01-01T00:00:00", line=1, value="v"):
    model, res_id, field, lang = key
    rec = {"ts": ts, "event": event, "row_id": "68:x", "site": 68, "campo": "x", "model": model,
           "res_id": res_id, "field": field, "lang": lang, "applied": event == "applied", "_line": line}
    if event == "backup":
        rec["valor_anterior"] = value
        rec["valor_nuevo"] = "new"
    return rec


class RevertirCollectTests(unittest.TestCase):
    def test_earliest_backup_and_events(self):
        k_applied = ("ir.ui.view", 1, "arch_db", "es_ES")
        k_pending = ("ir.ui.view", 1, "arch_db", "en_US")
        k_backup_only = ("res.company", 68, "microsite_hero_image", None)
        records = [
            _rec("backup", k_applied, ts="2026-01-01T00:00:01", line=1, value="ORIGINAL"),
            _rec("pending", k_applied, ts="2026-01-01T00:00:02", line=2),
            _rec("applied", k_applied, ts="2026-01-01T00:00:03", line=3),
            _rec("backup", k_applied, ts="2026-01-02T00:00:00", line=4, value="SECOND RUN"),
            _rec("backup", k_pending, ts="2026-01-01T00:00:01", line=5, value="P0"),
            _rec("pending", k_pending, ts="2026-01-01T00:00:02", line=6),
            _rec("backup", k_backup_only, ts="2026-01-01T00:00:01", line=7, value="IMG"),
        ]
        restores = {(r.model, r.res_id, r.field, r.lang): r for r in revertir.collect_restores(records)}
        self.assertEqual(len(restores), 3)
        self.assertEqual(restores[k_applied].valor_anterior, "ORIGINAL")
        self.assertTrue(restores[k_applied].applied)
        self.assertTrue(restores[k_pending].applied)  # pending counts as attempted
        self.assertFalse(restores[k_backup_only].applied)

    def test_writer_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.jsonl"
            w = lib.BackupWriter(path)
            w.open()
            fields = dict(site=68, campo="x", model="res.company", res_id=68, field="f", lang=None)
            w.append_backup(**fields, valor_anterior="a", valor_nuevo="b")
            w.append_pending(**fields)
            w.append_applied(**fields)
            w.close()
            events = [r["event"] for r in lib.read_backup(path)]
        self.assertEqual(events, ["backup", "pending", "applied"])


# ---------------------------------------------------------------------------
# aplicar end-to-end with an in-memory client
# ---------------------------------------------------------------------------

class FakeClient:
    """In-memory stand-in for :class:`lib.OdooClient`."""

    def __init__(self, langs, websites, pages, companies, views):
        self.uid = 1
        self.langs = langs
        self.websites = websites      # site -> company_id
        self.pages = pages            # site -> homepage view id
        self.companies = companies    # company_id -> {field: value}
        self.views = views            # view_id -> {lang: arch}
        self.fail_writes: set[tuple] = set()   # (model, res_id, field)
        self.writes: list[tuple] = []

    def language_codes(self, primary=lib.DEFAULT_PRIMARY_LANG):
        return lib.order_languages(self.langs, primary)

    def company_of_website(self, site):
        if site not in self.websites:
            raise lib.OdooError(f"website {site} not found")
        return self.websites[site]

    def homepage_view_id(self, site):
        return self.pages.get(site)

    def read_one(self, model, res_id, fields, context=None):
        if model == lib.MODEL_COMPANY:
            rec = self.companies[res_id]
            return {"id": res_id, **{f: rec.get(f, False) for f in fields}}
        if model == lib.MODEL_VIEW:
            lang = (context or {}).get("lang", lib.DEFAULT_PRIMARY_LANG)
            return {"id": res_id, lib.FIELD_ARCH: self.views[res_id][lang]}
        raise lib.OdooError(f"unknown model {model}")

    def read_arch(self, view_id, lang):
        return self.views[view_id][lang]

    def write(self, model, ids, values, context=None):
        for res_id in ids:
            for field_name, value in values.items():
                if (model, res_id, field_name) in self.fail_writes:
                    raise lib.OdooError(f"{model}.write: simulated failure")
                self.writes.append((model, res_id, field_name, (context or {}).get("lang")))
                if model == lib.MODEL_COMPANY:
                    self.companies[res_id][field_name] = value
                elif model == lib.MODEL_VIEW:
                    self.views[res_id][context["lang"]] = value
        return True


CSV_HEADER = "site,campo,valor_anterior,valor_nuevo,confianza,motivo\n"


class AplicarEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.zip_root = self.dir / "zip"
        (self.zip_root / "littlebeach" / "hero").mkdir(parents=True)
        self.image = self.zip_root / "littlebeach" / "hero" / "portada.png"
        self.image.write_bytes(b"\x89PNG fake")
        self.encoded = base64.b64encode(self.image.read_bytes()).decode("ascii")
        self.backup = self.dir / "backup.jsonl"
        self.csv = self.dir / "cambios.csv"
        self.client = FakeClient(
            langs=["en_US", "es_ES"], websites={68: 68}, pages={68: 3352},
            companies={68: {"microsite_intro_title": "Bienvenidos a nuestro espacio", "microsite_hero_image": False}},
            views={3352: {"es_ES": ARCH, "en_US": ARCH.replace("Bienvenidos a nuestro espacio", "Welcome to our space")}},
        )
        self.patcher = mock.patch.object(lib, "client_from_args", lambda args: self.client)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def write_csv(self, rows):
        lines = [CSV_HEADER]
        for site, campo, prev, new in rows:
            lines.append(f'"{site}","{campo}","{prev}","{new}","0.98","m"\n')
        self.csv.write_text("".join(lines), encoding="utf-8")

    def run_main(self, *extra):
        out = io.StringIO()
        argv = ["--db", "test", "--csv", str(self.csv), "--zip-root", str(self.zip_root),
                "--backup", str(self.backup), *extra]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = aplicar.main(argv)
        return code, out.getvalue()

    STANDARD_ROWS = [
        (68, "res_company.microsite_hero_image", "", "littlebeach/hero/portada.png"),
        (68, "ir_ui_view.3352.Hero.bg", "/web/image/ir.attachment/4773/datas", "littlebeach/hero/portada.png"),
        (68, "res_company.microsite_intro_title", "Bienvenidos a nuestro espacio", "Playa chica"),
        (68, "ir_ui_view.3352.SEC1.insert", "", "Playa chica"),
    ]

    def test_dry_run_writes_nothing(self):
        self.write_csv(self.STANDARD_ROWS)
        code, out = self.run_main()
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("WOULD APPLY"), 4)
        self.assertEqual(self.client.writes, [])
        self.assertFalse(self.backup.exists())

    def test_apply_twice_is_idempotent(self):
        self.write_csv(self.STANDARD_ROWS)
        code, out = self.run_main("--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("APPLIED"), 4)
        self.assertEqual(self.client.companies[68]["microsite_hero_image"], self.encoded)
        self.assertEqual(self.client.companies[68]["microsite_intro_title"], "Playa chica")
        for lang in ("es_ES", "en_US"):
            arch = self.client.views[3352][lang]
            self.assertEqual(lib.extract_section_bg(arch, "Hero"), URL_68_HERO)
            self.assertEqual(lib.extract_section_h2(arch, "SEC1"), "Playa chica")
        # company writes first (KIND_ORDER: fields, then images), then one
        # arch write per language with both view rows combined
        self.assertEqual(self.client.writes[:2], [("res.company", 68, "microsite_intro_title", None),
                                                  ("res.company", 68, "microsite_hero_image", None)])
        self.assertEqual([w[3] for w in self.client.writes[2:]], ["es_ES", "en_US"])
        records = lib.read_backup(self.backup)
        events = [r["event"] for r in records]
        self.assertEqual(events.count("backup"), 6)   # 2 company + 2 rows x 2 langs
        self.assertEqual(events.count("pending"), 6)
        self.assertEqual(events.count("applied"), 6)
        self.assertLess(events.index("pending"), events.index("applied"))
        self.assertTrue(all(e == "backup" for e in events[:6]))
        original = next(r for r in records if r["event"] == "backup" and r["lang"] == "es_ES")
        self.assertEqual(original["valor_anterior"], ARCH)

        writes_before = list(self.client.writes)
        code, out = self.run_main("--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("already applied"), 4)
        self.assertEqual(self.client.writes, writes_before)

    def test_dependency_failure_marks_bg_row_failed(self):
        self.write_csv(self.STANDARD_ROWS)
        self.client.fail_writes.add(("res.company", 68, "microsite_hero_image"))
        code, out = self.run_main("--apply")
        self.assertEqual(code, 1)
        self.assertIn("ir_ui_view.3352.Hero.bg", out)
        self.assertRegex(out, r"Hero\.bg\s+FAIL.*depends on failed write res\.company\[68\]\.microsite_hero_image")
        for lang in ("es_ES", "en_US"):
            arch = self.client.views[3352][lang]
            self.assertEqual(lib.extract_section_bg(arch, "Hero"), "/web/image/ir.attachment/4773/datas")
            self.assertEqual(lib.extract_section_h2(arch, "SEC1"), "Playa chica")   # sibling row still written
        self.assertEqual(self.client.companies[68]["microsite_intro_title"], "Playa chica")
        events = [r["event"] for r in lib.read_backup(self.backup)]
        # pending: intro_title, hero_image (failed), arch es_ES, arch en_US
        self.assertEqual(events.count("pending"), 4)
        self.assertEqual(events.count("applied"), 3)

    def test_partial_language_completion(self):
        self.write_csv(self.STANDARD_ROWS[2:])
        # es_ES already transformed, en_US not: complete en_US without blocking.
        self.client.views[3352]["es_ES"] = lib.insert_sec1_after_hero(ARCH, "Playa chica")
        self.client.companies[68]["microsite_intro_title"] = "Playa chica"
        code, out = self.run_main("--apply")
        self.assertEqual(code, 0, out)
        self.assertIn("completing 1 language(s), primary already applied", out)
        self.assertEqual(self.client.writes, [("ir.ui.view", 3352, "arch_db", "en_US")])
        self.assertEqual(lib.extract_section_h2(self.client.views[3352]["en_US"], "SEC1"), "Playa chica")

    def test_changed_on_server_and_scoped_force(self):
        self.write_csv([(68, "ir_ui_view.3352.Hero.h2", "Otra cosa", "Nuevo titular")])
        code, out = self.run_main("--apply")
        self.assertEqual(code, 0, out)
        self.assertIn("changed on server since analysis", out)
        self.assertEqual(self.client.writes, [])
        code, out = self.run_main("--apply", "--force", "--only-site", "68")
        self.assertEqual(code, 0, out)
        self.assertIn("FORCED", out)
        self.assertEqual(lib.extract_section_h2(self.client.views[3352]["es_ES"], "Hero"), "Nuevo titular")
        self.assertEqual(lib.extract_section_h2(self.client.views[3352]["en_US"], "Hero"), "Nuevo titular")

    def test_force_requires_only_site(self):
        self.write_csv(self.STANDARD_ROWS)
        with self.assertRaises(SystemExit) as ctx, contextlib.redirect_stderr(io.StringIO()):
            aplicar.main(["--force", "--csv", str(self.csv)])
        self.assertEqual(ctx.exception.code, 2)

    def test_view_ownership(self):
        self.write_csv([(68, "ir_ui_view.9999.Hero.h2", "Bienvenidos a nuestro espacio", "X")])
        self.client.views[9999] = dict(self.client.views[3352])
        code, out = self.run_main("--apply")
        self.assertEqual(code, 1)
        self.assertIn("view 9999 is not the homepage view of site 68 (homepage view is 3352)", out)
        self.assertEqual(self.client.writes, [])
        self.client.pages = {}
        code, out = self.run_main("--apply")
        self.assertIn("has no homepage page", out)

    def test_image_changed_on_server(self):
        self.write_csv(self.STANDARD_ROWS[:2])
        self.client.companies[68]["microsite_hero_image"] = base64.b64encode(b"other").decode("ascii")
        code, out = self.run_main("--apply")
        self.assertEqual(code, 1, out)
        self.assertRegex(out, r"microsite_hero_image\s+SKIP.*changed on server")
        self.assertRegex(out, r"Hero\.bg\s+FAIL.*depends on skipped row")
        self.assertEqual(self.client.writes, [])
        # equal image -> already applied, and the bg row proceeds
        self.client.companies[68]["microsite_hero_image"] = self.encoded
        code, out = self.run_main("--apply")
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"microsite_hero_image\s+SKIP.*already applied")
        self.assertEqual(lib.extract_section_bg(self.client.views[3352]["es_ES"], "Hero"), URL_68_HERO)

    def test_zip_escape_and_bad_url_fail_rows(self):
        self.write_csv([
            (68, "res_company.microsite_hero_image", "", "../outside.png"),
            (68, "ir_ui_view.3352.Hero.bg", "/web/image/ir.attachment/4773/datas", "/web/image/res.company/69/microsite_hero_image"),
            (68, "ir_ui_view.3352.SEC1.bg", "", "/web/image/ir.attachment/1/datas"),
        ])
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertRegex(out, r"microsite_hero_image\s+FAIL.*'\.\.' not allowed")
        self.assertRegex(out, r"Hero\.bg\s+FAIL.*does not belong to company 68")
        self.assertRegex(out, r"SEC1\.bg\s+FAIL.*not allowed")

    def test_offline_validation(self):
        self.write_csv(self.STANDARD_ROWS + [
            (69, "res_company.microsite_hero_image", "", "/etc/passwd"),
            (69, "res_company.category_id", "", "abc"),
            (69, "ir_ui_view.1.Hero.bg", "", "/web/image/res.company/1/microsite_hero_image"),
            (70, "ir_ui_view.2.Hero.bg", "", "missing/hero.png"),
            (70, "res_company.microsite_intro_title", "", "a"),
            (70, "res_company.microsite_intro_title", "", "b"),
        ])
        code, out = self.run_main("--offline")
        self.assertEqual(code, 1)
        self.assertIn("deferred to the connected run", out)
        self.assertIn("would apply: 5", out)
        self.assertIn("failed:  5", out)
        self.assertIn("duplicated (site, campo)", out)
        self.assertRegex(out, r"category_id\s+FAIL.*integer id")
        self.assertRegex(out, r"microsite_hero_image\s+FAIL.*absolute")
        self.assertRegex(out, r"ir_ui_view\.2\.Hero\.bg\s+FAIL.*no res_company\.microsite_hero_image row")
        self.assertEqual(self.client.writes, [])

    def write_rows_csv(self, rows):
        """CSV with proper quoting (values may contain quotes / JSON)."""
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(["site", "campo", "valor_anterior", "valor_nuevo", "confianza", "motivo"])
        for site, campo, prev, new in rows:
            writer.writerow([site, campo, prev, new, "0.98", "m"])
        self.csv.write_text(buf.getvalue(), encoding="utf-8")

    def test_sec1_then_acerca_insert_end_to_end(self):
        base = NO_ACERCA_NO_SEC1
        self.client.views[3352] = {"es_ES": base, "en_US": base.replace("Hola", "Hello")}
        self.client.companies[68].update(microsite_about_text=False, microsite_services_text="Viejo")
        # CSV order deliberately puts the Acerca rows before the SEC1 insert.
        self.write_rows_csv([
            (68, "ir_ui_view.3352.Acerca.col2", "", "Servicios finales"),
            (68, "ir_ui_view.3352.Acerca.insert", "", json.dumps(PAYLOAD, ensure_ascii=False)),
            (68, "ir_ui_view.3352.SEC1.insert", "", "Playa chica"),
            (68, "res_company.microsite_about_text", "", PAYLOAD["about"]),
            (68, "res_company.microsite_services_text", "Viejo", PAYLOAD["services"]),
        ])
        code, out = self.run_main("--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("APPLIED"), 5, out)
        self.assertEqual(self.client.companies[68]["microsite_about_text"], PAYLOAD["about"])
        self.assertEqual(self.client.companies[68]["microsite_services_text"], PAYLOAD["services"])
        for lang in ("es_ES", "en_US"):
            arch = self.client.views[3352][lang]
            hero, sec1, acerca = (lib.find_section(arch, n) for n in ("Hero", "SEC1", "Acerca"))
            self.assertLess(hero.end, sec1.start)
            self.assertLess(sec1.end, acerca.start)
            self.assertEqual(lib.extract_acerca_column(arch, 1), PAYLOAD["about"])
            self.assertEqual(lib.extract_acerca_column(arch, 2), "Servicios finales")
        # one arch write per language, all view rows combined
        self.assertEqual([w for w in self.client.writes if w[0] == "ir.ui.view"],
                         [("ir.ui.view", 3352, "arch_db", "es_ES"), ("ir.ui.view", 3352, "arch_db", "en_US")])

        writes_before = list(self.client.writes)
        code, out = self.run_main("--apply")
        self.assertEqual(code, 0, out)
        # the insert row now reads a different col2 than its payload: it is
        # "changed on server", never re-inserted; the rest is already applied
        self.assertEqual(out.count("already applied"), 4, out)
        self.assertRegex(out, r"Acerca\.insert\s+SKIP.*changed on server")
        self.assertEqual(self.client.writes, writes_before)

    def test_acerca_insert_idempotent_and_column_append(self):
        self.client.views[3352] = {"es_ES": NO_ACERCA, "en_US": NO_ACERCA}
        self.write_rows_csv([(68, "ir_ui_view.3352.Acerca.insert", "", json.dumps(PAYLOAD))])
        code, out = self.run_main("--apply")
        self.assertEqual(code, 0, out)
        code, out = self.run_main("--apply")
        self.assertEqual(code, 0, out)
        self.assertIn("already applied", out)
        self.assertEqual(len(self.client.writes), 2)

        self.client.views[3352] = {"es_ES": LEGACY_ONE, "en_US": LEGACY_ONE}
        self.client.writes = []
        self.write_rows_csv([(68, "ir_ui_view.3352.Acerca.col2", "", "Nuevos servicios")])
        code, out = self.run_main("--apply")
        self.assertEqual(code, 0, out)
        self.assertIn("column 2 appended", out)
        self.assertIn('id="acerca2_lapapayafitnesscenter"', self.client.views[3352]["en_US"])
        code, out = self.run_main("--apply")
        self.assertIn("already applied", out)
        self.assertEqual(len(self.client.writes), 2)

    def test_acerca_insert_refused_when_present(self):
        self.client.views[3352] = {"es_ES": LEGACY_TWO, "en_US": LEGACY_TWO}
        self.write_rows_csv([(68, "ir_ui_view.3352.Acerca.insert", "", json.dumps(PAYLOAD))])
        code, out = self.run_main("--apply", "--force", "--only-site", "68")
        self.assertEqual(code, 1, out)
        self.assertRegex(out, r"Acerca\.insert\s+FAIL.*already exists")
        self.assertEqual(self.client.writes, [])

    def test_acerca_column_drift(self):
        self.client.views[3352] = {"es_ES": LEGACY_TWO, "en_US": LEGACY_TWO}
        self.write_rows_csv([(68, "ir_ui_view.3352.Acerca.col1", "Otra  historia", "Nueva")])
        code, out = self.run_main("--apply")
        self.assertRegex(out, r"Acerca\.col1\s+SKIP.*changed on server")
        self.assertEqual(self.client.writes, [])
        self.write_rows_csv([(68, "ir_ui_view.3352.Acerca.col1", " Historia\n completa ", "Nueva")])
        code, out = self.run_main("--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(lib.extract_acerca_column(self.client.views[3352]["es_ES"], 1), "Nueva")

    def test_acerca_insert_anchor_must_match_across_languages(self):
        self.client.views[3352] = {"es_ES": NO_ACERCA, "en_US": NO_ACERCA_NO_SEC1}
        self.write_rows_csv([(68, "ir_ui_view.3352.Acerca.insert", "", json.dumps(PAYLOAD))])
        code, out = self.run_main("--apply")
        self.assertEqual(code, 1, out)
        self.assertRegex(out, r"Acerca\.insert\s+FAIL.*anchor differs")
        self.assertIn("es_ES=SEC1", out)
        self.assertIn("en_US=Hero", out)
        self.assertEqual(self.client.writes, [])

    def test_acerca_offline_validation(self):
        self.write_rows_csv([
            (68, "ir_ui_view.3352.Acerca.insert", "", json.dumps(PAYLOAD)),
            (68, "ir_ui_view.3352.Acerca.col1", "", "Texto"),
            (69, "ir_ui_view.1.Acerca.insert", "", "{not json"),
            (69, "ir_ui_view.1.Acerca.col2", "", "   "),
            (69, "ir_ui_view.1.Acerca.h2", "", "x"),
            (70, "ir_ui_view.2.Acerca.insert", "", json.dumps(dict(PAYLOAD, about=""))),
            (70, "ir_ui_view.2.Acerca.col3", "", "x"),
        ])
        code, out = self.run_main("--offline")
        self.assertEqual(code, 1)
        self.assertIn("would apply: 2", out)
        self.assertIn("failed:  5", out)
        self.assertRegex(out, r"ir_ui_view\.1\.Acerca\.insert\s+FAIL.*not valid JSON")
        self.assertRegex(out, r"ir_ui_view\.1\.Acerca\.col2\s+FAIL.*empty text")
        self.assertRegex(out, r"ir_ui_view\.1\.Acerca\.h2\s+FAIL.*unsupported op 'h2'")
        self.assertRegex(out, r"ir_ui_view\.2\.Acerca\.insert\s+FAIL.*must not be empty")
        self.assertRegex(out, r"Acerca\.col3.*FAIL.*unsupported column op")

    def test_prod_requires_confirmation_without_tty(self):
        self.write_csv(self.STANDARD_ROWS)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out), \
                mock.patch.object(sys.stdin, "isatty", lambda: False):
            code = aplicar.main(["--apply", "--db", "prod", "--csv", str(self.csv),
                                 "--zip-root", str(self.zip_root), "--backup", str(self.backup)])
        self.assertEqual(code, 2)
        self.assertIn("refusing to --apply on db 'prod'", out.getvalue())
        self.assertEqual(self.client.writes, [])


class CredentialsTests(unittest.TestCase):
    def test_no_password_flag(self):
        parser = aplicar.build_parser()
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            parser.parse_args(["--password", "x"])

    def test_password_without_tty(self):
        with mock.patch.dict(os.environ, {"ODOO_PASSWORD": ""}), \
                mock.patch.object(sys.stdin, "isatty", lambda: False):
            with self.assertRaises(lib.CredentialsError):
                lib.resolve_password("admin", "test")
        with mock.patch.dict(os.environ, {"ODOO_PASSWORD": "secret"}):
            self.assertEqual(lib.resolve_password("admin", "test"), "secret")


if __name__ == "__main__":
    unittest.main()
