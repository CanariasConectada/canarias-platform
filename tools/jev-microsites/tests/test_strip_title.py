"""Tests for the strip-2 ("Separador") title path: library checks, aplicar
offline/connected flow, the hand-translation planner and the proposal rules.

No network, no database. Run from the tool directory with
``python3 -m unittest``.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from collections import Counter
from datetime import datetime
from pathlib import Path
from unittest import mock

TOOL_DIR = Path(__file__).resolve().parents[1]
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

import aplicar  # noqa: E402
import corregir_traducciones  # noqa: E402
import jev_apply_lib as lib  # noqa: E402
import propuesta_s2  # noqa: E402
from tests.test_jev_apply_lib import ARCH, CSV_HEADER, FakeClient  # noqa: E402

VIEW = "ir_ui_view.3352.Separador.h2"
FIELD = "res_company.microsite_banner_title"
OLD = "Llámanos"
NEW = "Little Beach: cócteles y deporte en directo"


def change(site, campo, prev, new, line=1):
    return lib.Change(site, campo, prev, new, 0.9, "m", lib.parse_campo(campo), line)


class CheckStripTitleTests(unittest.TestCase):
    def test_accepts_sentence_case_title(self):
        self.assertEqual(lib.check_strip_title(NEW), "")

    def test_brand_in_capitals_inside_a_sentence_is_fine(self):
        self.assertEqual(lib.check_strip_title("MUNDO BURGER, hamburguesería en Guanarteme"), "")

    def test_rejects_all_capitals(self):
        self.assertIn("capitals", lib.check_strip_title("CONSUME PRODUCTOS CANARIOS"))

    def test_rejects_empty_long_multiline_markup_and_padding(self):
        self.assertIn("empty", lib.check_strip_title("   "))
        self.assertIn("max 60", lib.check_strip_title("a" * 61))
        self.assertEqual(lib.check_strip_title("a" * 60), "")
        self.assertIn("single line", lib.check_strip_title("uno\ndos"))
        self.assertIn("markup", lib.check_strip_title("Hola <b>tú</b>"))
        self.assertIn("whitespace", lib.check_strip_title(" Hola"))


class StripTargetTests(unittest.TestCase):
    def test_targets(self):
        self.assertTrue(lib.is_strip_title_target(lib.parse_campo(VIEW)))
        self.assertTrue(lib.is_strip_title_target(lib.parse_campo(FIELD)))
        self.assertFalse(lib.is_strip_title_target(lib.parse_campo("ir_ui_view.3352.SEC1.h2")))
        self.assertFalse(lib.is_strip_title_target(lib.parse_campo("res_company.microsite_intro_title")))

    def test_pair_error(self):
        view = change(68, VIEW, OLD, NEW, 1)
        company = change(68, FIELD, "", NEW, 2)
        self.assertEqual(lib.strip_title_pair_error(view, [view, company]), "")
        self.assertIs(lib.strip_title_sibling(view, [view, company]), company)
        self.assertIs(lib.strip_title_sibling(company, [view, company]), view)
        self.assertIn("no res_company", lib.strip_title_pair_error(view, [view]))
        other = change(68, FIELD, "", "Otra cosa distinta", 2)
        self.assertIn("different text", lib.strip_title_pair_error(view, [view, other]))
        # a company row alone (dynamic template) is valid
        self.assertEqual(lib.strip_title_pair_error(company, [company]), "")
        # a sibling of another site does not count
        foreign = change(69, FIELD, "", NEW, 3)
        self.assertIn("no res_company", lib.strip_title_pair_error(view, [view, foreign]))

    def test_view_ids_of_changes(self):
        rows = [change(68, VIEW, OLD, NEW), change(68, FIELD, "", NEW),
                change(70, "ir_ui_view.12.Separador.h2", "x", NEW)]
        self.assertEqual(lib.view_ids_of_changes(rows), [12, 3352])

    def test_replace_strip_heading_keeps_the_rest_of_the_arch(self):
        out = lib.replace_section_h2(ARCH, lib.STRIP_SECTION, "M&G Moda: moda y complementos")
        self.assertEqual(lib.extract_section_h2(out, lib.STRIP_SECTION), "M&G Moda: moda y complementos")
        self.assertIn("M&amp;G Moda", out)
        self.assertEqual(out.replace("M&amp;G Moda: moda y complementos", "Ll&aacute;manos"), ARCH)


class AplicarStripTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.csv = self.dir / "cambios_s2.csv"
        self.backup = self.dir / "backup.jsonl"
        self.client = FakeClient(
            langs=["en_US", "es_ES"], websites={68: 68}, pages={68: 3352},
            companies={68: {"microsite_banner_title": "Consume Productos Canarios"}},
            views={3352: {"es_ES": ARCH, "en_US": ARCH}})
        self.patcher = mock.patch.object(lib, "client_from_args", lambda args: self.client)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def write_csv(self, rows):
        lines = [CSV_HEADER] + [f'"{s}","{c}","{p}","{n}","0.95","m"\n' for s, c, p, n in rows]
        self.csv.write_text("".join(lines), encoding="utf-8")

    def run_main(self, *extra):
        out = io.StringIO()
        argv = ["--db", "test", "--csv", str(self.csv), "--backup", str(self.backup), *extra]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = aplicar.main(argv)
        return code, out.getvalue()

    PAIR = [(68, VIEW, OLD, NEW), (68, FIELD, "Consume Productos Canarios", NEW)]

    def test_offline_accepts_a_valid_pair(self):
        self.write_csv(self.PAIR)
        code, out = self.run_main("--offline")
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("PLAN"), 2)

    def test_offline_rejects_unpaired_or_invalid_titles(self):
        self.write_csv([(68, VIEW, OLD, NEW)])
        code, out = self.run_main("--offline")
        self.assertEqual(code, 1)
        self.assertIn("no res_company.microsite_banner_title row", out)
        self.write_csv([(68, VIEW, OLD, "TODO EN MAYÚSCULAS"), (68, FIELD, "", "TODO EN MAYÚSCULAS")])
        code, out = self.run_main("--offline")
        self.assertEqual(code, 1)
        self.assertEqual(out.count("all capitals"), 2)

    def test_apply_writes_heading_and_field(self):
        self.write_csv(self.PAIR)
        code, out = self.run_main("--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.client.companies[68]["microsite_banner_title"], NEW)
        self.assertEqual(lib.extract_section_h2(self.client.views[3352]["es_ES"], "Separador"), NEW)
        self.assertEqual(self.client.writes, [("res.company", 68, "microsite_banner_title", None),
                                              ("ir.ui.view", 3352, "arch_db", "es_ES")])
        events = [r["event"] for r in lib.read_backup(self.backup)]
        self.assertEqual(events.count("backup"), 2)
        code, out = self.run_main("--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("already applied"), 2)

    def test_heading_changed_on_server_leaves_the_field_alone(self):
        self.client.views[3352]["es_ES"] = lib.replace_section_h2(ARCH, "Separador", "Escrito por el comercio")
        self.write_csv(self.PAIR)
        code, out = self.run_main("--apply")
        self.assertEqual(code, 0, out)
        self.assertIn("changed on server", out)
        self.assertIn("paired strip heading", out)
        self.assertEqual(self.client.writes, [])
        self.assertEqual(self.client.companies[68]["microsite_banner_title"], "Consume Productos Canarios")
        self.assertFalse(any(r["event"] == "backup" for r in lib.read_backup(self.backup)))

    def test_field_changed_on_server_leaves_the_heading_alone(self):
        self.client.companies[68]["microsite_banner_title"] = "Puesto a mano"
        self.write_csv(self.PAIR)
        code, out = self.run_main()
        self.assertEqual(code, 0, out)
        self.assertIn("paired res_company.microsite_banner_title row is not applied", out)
        self.assertNotIn("WOULD APPLY", out)

    def test_heading_on_a_view_that_is_not_the_homepage_fails_and_releases_the_field(self):
        self.write_csv([(68, "ir_ui_view.999.Separador.h2", OLD, NEW), (68, FIELD, "Consume Productos Canarios", NEW)])
        code, out = self.run_main("--apply")
        self.assertEqual(code, 1)
        self.assertIn("is not the homepage view", out)
        self.assertEqual(self.client.writes, [])

    def test_dynamic_site_with_field_only(self):
        self.write_csv([(68, FIELD, "Consume Productos Canarios", NEW)])
        code, out = self.run_main("--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.client.writes, [("res.company", 68, "microsite_banner_title", None)])


class CorregirTraduccionesPlanTests(unittest.TestCase):
    TR = {"M&amp;G Moda: moda": {"en_US": "M&amp;G Moda: fashion", "de_DE": "M&amp;G Moda: Mode"}}

    def term(self, lang, translated, source="M&amp;G Moda: moda"):
        return {"id": 1, "lang": lang, "source_text": source, "translated_text": translated, "state": "auto"}

    def test_plan(self):
        terms = [self.term("en_US", "M&amp;G Fashion: fashion"), self.term("de_DE", "M&amp;G Moda: Mode"),
                 self.term("fr_FR", "x"), self.term("en_US", "y", source="Otra frase")]
        todo, counts = corregir_traducciones.plan_term_writes(terms, self.TR, None)
        self.assertEqual([(t["lang"], new) for t, new in todo], [("en_US", "M&amp;G Moda: fashion")])
        self.assertEqual(counts, {"same": 1, "held_back": 0, "unknown": 1})

    def test_plan_holds_back_by_qa(self):
        qa = {"M&amp;G Moda: moda": {"en_US": {"ok": False, "p": 0.5}, "de_DE": {"ok": True, "p": 0.9}}}
        todo, counts = corregir_traducciones.plan_term_writes([self.term("en_US", False)], self.TR, qa)
        self.assertEqual(todo, [])
        self.assertEqual(counts["held_back"], 1)

    def test_view_ids_from_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.csv"
            path.write_text(CSV_HEADER + f'"68","{VIEW}","a","{NEW}","0.9","m"\n'
                            f'"68","{FIELD}","","{NEW}","0.9","m"\n', encoding="utf-8")
            self.assertEqual(corregir_traducciones.view_ids_from_args(None, str(path)), [3352])


class PropuestaRulesTests(unittest.TestCase):
    def site(self, **kw):
        base = {"website_id": 68, "dynamic": False, "sections": ["Hero", "SEC1", "Acerca", "Separador"],
                "texts": {"separador_h2": "Consume Productos Canarios"}, "view_id": 3352, "company_id": 68,
                "view_write_uid": 1, "view_write_date": "2026-09-30T05:56:00",
                "company_write_uid": 1, "company_write_date": "2026-09-30T05:56:00"}
        base.update(kw)
        return base

    COUNTS = Counter({"Consume Productos Canarios": 185, "CONSUME PRODUCTOS CANARIOS": 7, "Texto único": 1})

    def test_default_texts(self):
        self.assertTrue(propuesta_s2.is_default("CONSUME PRODUCTOS CANARIOS", self.COUNTS))
        self.assertTrue(propuesta_s2.is_default("", self.COUNTS))
        self.assertFalse(propuesta_s2.is_default("Texto único", self.COUNTS))

    def test_unique_text_is_excluded(self):
        status, _ = propuesta_s2.decide(self.site(texts={"separador_h2": "Texto único"}), NEW, self.COUNTS, {}, 0.9)
        self.assertEqual(status, propuesta_s2.STATUS_EXCLUDED)

    def test_change_needs_jev_score(self):
        self.assertEqual(propuesta_s2.decide(self.site(), NEW, self.COUNTS, {}, 0.9)[0], propuesta_s2.STATUS_CHANGE)
        self.assertEqual(propuesta_s2.decide(self.site(), NEW, self.COUNTS, {}, 0.8)[0], propuesta_s2.STATUS_REVIEW)
        self.assertEqual(propuesta_s2.decide(self.site(), NEW, self.COUNTS, {}, None)[0], propuesta_s2.STATUS_REVIEW)

    def test_person_edit_goes_to_review_but_own_apply_run_does_not(self):
        site = self.site(company_write_uid=207, company_write_date="2026-09-23T09:10:30")
        status, motivo = propuesta_s2.decide(site, NEW, self.COUNTS, {}, 0.9)
        self.assertEqual(status, propuesta_s2.STATUS_REVIEW)
        self.assertIn("uid 207", motivo)
        events = {("res.company", 68): [datetime(2026, 9, 23, 9, 10, 2)]}
        self.assertEqual(propuesta_s2.decide(site, NEW, self.COUNTS, events, 0.9)[0], propuesta_s2.STATUS_CHANGE)

    def test_page_without_strip_goes_to_review(self):
        site = self.site(sections=["Hero", "SEC1", "Acerca"], texts={})
        status, motivo = propuesta_s2.decide(site, NEW, self.COUNTS, {}, 0.95)
        self.assertEqual(status, propuesta_s2.STATUS_REVIEW)
        self.assertIn("Separador", motivo)

    def test_arch_text_escapes_ampersand(self):
        self.assertEqual(propuesta_s2.arch_text("M&G Moda"), "M&amp;G Moda")


if __name__ == "__main__":
    unittest.main()
