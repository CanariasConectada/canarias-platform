"""Homepage rebuild: text extraction, rendering per language, validation and
term alignment (``jev_rebuild_lib``, ``jev_rebuild_check``, ``jev_rebuild_terms``)."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jev_apply_lib as lib  # noqa: E402
import jev_rebuild_check as check  # noqa: E402
import jev_rebuild_lib as rb  # noqa: E402
import jev_rebuild_terms as terms  # noqa: E402
import rebuild_fixtures as fx  # noqa: E402

STANDARD = list(rb.STANDARD_ORDER)


class ExtractTermsTests(unittest.TestCase):
    def test_inline_children_join_the_parent_term(self):
        arch = ('<div><h1 class="x"><span class="display-4-fs">Flash &amp; Print</span></h1>'
                '<p><a class="btn o_translate_inline" href="/shop">Tienda</a></p>'
                '<h4><span class="fa fa-envelope" style="m"/><strong>ESCRÍBENOS</strong></h4>'
                '<label><span class="a">Nombre</span><span class="b"> *</span></label>'
                '<img alt="Subvenciones"/><t t-call="x"/><p t-if="y"><t t-call="z"/></p><p>   </p></div>')
        self.assertEqual(terms.extract_terms(arch), [
            '<span class="display-4-fs">Flash &amp; Print</span>',
            '<a class="btn o_translate_inline" href="/shop">Tienda</a>',
            '<span class="fa fa-envelope" style="m"/><strong>ESCRÍBENOS</strong>',
            '<span class="a">Nombre</span><span class="b"> *</span>', 'Subvenciones'])

    def test_skipped_and_untranslated(self):
        arch = '<div><script>var a = "no";</script><p t-translation="off">no</p><h2 t-attf-title="x {{ a }} y">Hi</h2></div>'
        self.assertEqual(terms.extract_terms(arch), ["Hi", "x {{0}} y"])

    def test_malformed_raises(self):
        with self.assertRaises(terms.TermError):
            terms.extract_terms("<div><p>unclosed</div>")

    def test_mapping_pairs_by_position_and_skips_equal_terms(self):
        archs = {"es_ES": "<div><h2>Hola</h2><p>Email</p><img alt='Sub'/></div>",
                 "de_DE": "<div><h2>Hallo</h2><p>Email</p><img alt='Zus'/></div>"}
        self.assertEqual(terms.translation_mapping(archs, "es_ES"), {"de_DE": {"Hola": "Hallo", "Sub": "Zus"}})

    def test_mapping_refuses_misaligned_or_conflicting(self):
        with self.assertRaises(terms.TermError):
            terms.translation_mapping({"es_ES": "<div><h2>A</h2></div>", "de_DE": "<div><h2>A</h2><p>B</p></div>"}, "es_ES")
        with self.assertRaises(terms.TermError):
            terms.translation_mapping({"es_ES": "<div><h2>A</h2><p>A</p></div>",
                                       "de_DE": "<div><h2>B</h2><p>C</p></div>"}, "es_ES")
        with self.assertRaises(terms.TermError):
            terms.translation_mapping({"de_DE": "<div/>"}, "es_ES")

    def test_oracle_agrees_when_odoo_is_importable(self):
        arch = fx.reference_archs()["es_ES"]
        oracle = terms.oracle_terms(arch)
        if oracle is None:
            self.skipTest("Odoo source tree not importable")
        self.assertEqual(oracle, terms.extract_terms(arch))


class ExtractSiteTextsTests(unittest.TestCase):
    def test_standard_page(self):
        texts = rb.extract_site_texts(fx.deviating_archs()["es_ES"])
        self.assertEqual(texts.h1, "Área Surf & Skate")
        self.assertEqual(texts.sec1, "Tienda de surf en Guanarteme.")
        self.assertIsNone(texts.separador)
        self.assertEqual(texts.slug, "areasurf")
        self.assertEqual(texts.root_tag, '<t name="Home - areasurf" t-name="website.homepage_areasurf">')
        self.assertEqual(sorted(texts.columns), [1, 2])
        self.assertEqual(texts.columns[1].title, "Sobre nosotros")
        self.assertEqual(texts.columns[1].text, "Área Surf es una tienda para los que viven el mar.")
        self.assertEqual(texts.columns[1].excerpt, "Área Surf es una tienda para los que viven el mar.")

    def test_legacy_page_plain_h1_and_single_column(self):
        texts = rb.extract_site_texts(fx.legacy_archs()["de_DE"])
        self.assertEqual(texts.h1, "MAQUIFER INDUSTRIAL")
        self.assertEqual(texts.separador, "VERBRAUCH PRODUKTE KANARIEN")
        self.assertEqual(list(texts.columns), [1])
        self.assertEqual(texts.slug, "maquifercoop")

    def test_section_list(self):
        self.assertEqual(rb.section_list(fx.legacy_archs()["es_ES"]),
                         "Portada>Info Bar>SEC1>Acerca>Separador>Formulario Contacto>Formulario>Subvenciones")
        self.assertEqual(rb.section_names(fx.reference_archs()["es_ES"]), STANDARD)


class RebuildArchsTests(unittest.TestCase):
    def setUp(self):
        self.ref = fx.reference_archs()

    def test_deviating_site_gets_horario_and_separador(self):
        before = fx.deviating_archs()
        after, omitted, flags = rb.rebuild_archs(self.ref, before, fx.SITE["cid"], fx.SITE["slug"])
        self.assertEqual(omitted, [])
        self.assertEqual(set(after), set(fx.LANGS))
        for lang in fx.LANGS:
            self.assertEqual(rb.section_names(after[lang]), STANDARD, lang)
            self.assertNotIn("Flash Print", after[lang])
            self.assertNotIn("flashprint", after[lang])
            self.assertNotIn("res.company/51/", after[lang])
            self.assertIn(fx.TEMPLATE[lang]["hours"], after[lang])           # template text of that language
            self.assertIn(fx.TEMPLATE[lang]["strip"], after[lang])           # platform strip title, per language
            self.assertEqual(rb.extract_site_texts(after[lang]).preserved()["columns"],
                             rb.extract_site_texts(before[lang]).preserved()["columns"], lang)
        self.assertIn("Separador added with the platform title", " ".join(flags))
        self.assertEqual(check.validate_rebuilt(after, before, self.ref, fx.SITE["cid"], fx.SITE["slug"], omitted), [])
        self.assertEqual(after["es_ES"].count("acerca1_areasurf"), 2)
        self.assertEqual(len(re.findall(r"res\.company/285/microsite_(hero|intro|banner)_image", after["de_DE"])), 3)

    def test_existing_strip_title_is_kept_per_language(self):
        before = fx.deviating_archs(drop=("Horario",))
        after, _, _ = rb.rebuild_archs(self.ref, before, fx.SITE["cid"], fx.SITE["slug"])
        self.assertEqual(lib.extract_section_h2(after["de_DE"], "Separador"), "Verbrauch Produkte Kanarische Inseln")

    def test_legacy_layout(self):
        before = fx.legacy_archs()
        after, omitted, flags = rb.rebuild_archs(self.ref, before, fx.LEGACY["cid"], fx.LEGACY["slug"])
        self.assertEqual(omitted, [])
        self.assertEqual(rb.section_names(after["es_ES"]), STANDARD)
        self.assertTrue(after["es_ES"].startswith('<t name="Home - DiCloud - Error Interno" t-name="website.homepage_maquifercoop">'))
        self.assertEqual(lib.extract_section_h1(after["en_US"], "Hero"), "MAQUIFER INDUSTRIAL")
        self.assertIn('<span class="display-4-fs">Maquifer Industrial</span>', after["es_ES"])
        self.assertIn("col-lg-8 offset-lg-2", after["es_ES"])
        self.assertNotIn("acerca2_", after["es_ES"])
        self.assertNotIn("mycompany@test.com", after["es_ES"])
        self.assertNotIn("Info Bar", after["es_ES"])
        joined = " ".join(flags)
        for note in ("single column 1", "'Portada' dropped", "'Info Bar' dropped", "'Formulario Contacto' dropped",
                     "hardcoded contact text", "root tag kept verbatim"):
            self.assertIn(note, joined)
        self.assertEqual(check.validate_rebuilt(after, before, self.ref, fx.LEGACY["cid"], fx.LEGACY["slug"], omitted), [])

    def test_missing_sec1_and_acerca_are_omitted_never_invented(self):
        before = fx.legacy_archs(with_sec1=False)
        for lang in fx.LANGS:   # also drop the Acerca text
            before[lang] = rb._remove_section(before[lang], "Acerca")
        after, omitted, flags = rb.rebuild_archs(self.ref, before, fx.LEGACY["cid"], fx.LEGACY["slug"])
        self.assertEqual(omitted, ["SEC1", "Acerca"])
        for lang in fx.LANGS:
            self.assertEqual(rb.section_names(after[lang]), ["Hero", "Horario", "Separador", "Formulario", "Subvenciones"])
            self.assertNotIn("microsite_intro_image", after[lang])
            self.assertNotIn("acerca", after[lang])
        self.assertIn("SEC1 omitted", " ".join(flags))
        self.assertIn("Acerca omitted", " ".join(flags))
        self.assertEqual(check.validate_rebuilt(after, before, self.ref, fx.LEGACY["cid"], fx.LEGACY["slug"], omitted), [])

    def test_language_without_text_falls_back_to_primary_and_flags(self):
        before = fx.deviating_archs()
        before["de_DE"] = lib.replace_section_h2(before["de_DE"], "SEC1", " ")
        after, _, flags = rb.rebuild_archs(self.ref, before, fx.SITE["cid"], fx.SITE["slug"])
        self.assertEqual(lib.extract_section_h2(after["de_DE"], "SEC1"), "Tienda de surf en Guanarteme.")
        self.assertIn("de_DE: no sec1 text in that language, primary one used", flags)

    def test_errors(self):
        before = fx.deviating_archs()
        with self.assertRaises(rb.RebuildError):
            rb.rebuild_archs(self.ref, {k: v for k, v in before.items() if k != "de_DE"}, 285, "areasurf")
        with self.assertRaises(rb.RebuildError):
            rb.rebuild_archs(self.ref, before, 285, "bad slug!")
        no_h1 = {lang: arch.replace('<span class="display-4-fs">Área Surf &amp; Skate</span>', "") for lang, arch in before.items()}
        with self.assertRaises(rb.RebuildError):
            rb.rebuild_archs(self.ref, no_h1, 285, "areasurf")


class ValidateRebuiltTests(unittest.TestCase):
    def setUp(self):
        self.ref = fx.reference_archs()
        self.before = fx.deviating_archs()
        self.after, self.omitted, _ = rb.rebuild_archs(self.ref, self.before, fx.SITE["cid"], fx.SITE["slug"])

    def errors(self, after):
        return check.validate_rebuilt(after, self.before, self.ref, fx.SITE["cid"], fx.SITE["slug"], self.omitted)

    def test_detects_each_problem(self):
        broken = dict(self.after)
        broken["de_DE"] = broken["de_DE"].replace("</h2>", "", 1)
        self.assertTrue(any("not well-formed" in e for e in self.errors(broken)))
        leak = dict(self.after)
        leak["es_ES"] = lib.replace_section_h2(leak["es_ES"], "SEC1", "Flash Print: tu referente en Guanarteme.")
        self.assertTrue(any("reference text leaked" in e for e in self.errors(leak)))
        self.assertTrue(any("SEC1 text changed" in e for e in self.errors(leak)))
        wrong = dict(self.after)
        wrong["en_US"] = wrong["en_US"].replace("res.company/285/microsite_hero_image", "res.company/51/microsite_hero_image")
        self.assertTrue(any("company ids [51]" in e for e in self.errors(wrong)))
        slug = dict(self.after)
        slug["es_ES"] = slug["es_ES"].replace("acerca1_areasurf", "acerca1_flashprint")
        found = self.errors(slug)
        self.assertTrue(any("reference slug" in e for e in found) and any("collapse ids use slugs" in e for e in found))
        order = dict(self.after)
        order["es_ES"] = rb._remove_section(order["es_ES"], "Horario")
        self.assertTrue(any("section order" in e for e in self.errors(order)))
        misaligned = dict(self.after)
        misaligned["de_DE"] = misaligned["de_DE"].replace("<p class=\"text-muted\">", "<p class=\"text-muted\">Extra ", 1)
        self.assertTrue(any("terms do not line up" in e for e in self.errors(misaligned)))
        self.assertTrue(any("language keys" in e for e in self.errors({"es_ES": self.after["es_ES"]})))

    def test_clean_result_has_no_errors(self):
        self.assertEqual(self.errors(self.after), [])


if __name__ == "__main__":
    unittest.main()
