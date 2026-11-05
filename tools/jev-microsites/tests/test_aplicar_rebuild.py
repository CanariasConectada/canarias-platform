"""``Homepage.rebuild`` rows end to end: campo parsing, offline checks, the
backup file rule, planning against the server archs and the two-RPC write
(primary arch, then term translations) through a fake client that emulates
Odoo's term-based handling of ``arch_db``."""
from __future__ import annotations

import contextlib
import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import aplicar  # noqa: E402
import aplicar_rebuild as rebuild  # noqa: E402
import jev_apply_lib as lib  # noqa: E402
import jev_rebuild_lib as rb  # noqa: E402
import jev_rebuild_terms as terms  # noqa: E402
import rebuild_fixtures as fx  # noqa: E402
import test_jev_apply_lib as shared  # noqa: E402

VIEW, SITE, CID = 3717, 217, fx.SITE["cid"]
CAMPO = f"ir_ui_view.{VIEW}.Homepage.rebuild"


class TermAwareClient(shared.FakeClient):
    """Fake Odoo whose ``arch_db`` writes behave like the real xml_translate
    field: a write in language L rebuilds every other language term by
    term (known terms keep their translation, new ones read as written), and
    ``update_field_translations`` rebuilds the given languages from the
    source language through the mapping."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.translation_calls: list[tuple] = []

    def write(self, model, ids, values, context=None):
        if model != lib.MODEL_VIEW:
            return super().write(model, ids, values, context)
        lang = (context or {}).get("lang")
        for res_id in ids:
            if (model, res_id, lib.FIELD_ARCH) in self.fail_writes:
                raise lib.OdooError(f"{model}.write: simulated failure")
            self.writes.append((model, res_id, lib.FIELD_ARCH, lang))
            self.contexts.append(context)
            new = values[lib.FIELD_ARCH]
            old = self.views[res_id]
            old_terms = terms.extract_terms(old[lang])
            for other, arch in list(old.items()):
                if other == lang:
                    continue
                other_terms = terms.extract_terms(arch)
                known = dict(zip(old_terms, other_terms)) if len(old_terms) == len(other_terms) else {}
                old[other] = fx.translate_arch(new, lambda term, k=known: k.get(term))
            old[lang] = new
        return True

    def update_field_translations(self, model, res_id, field, translations, source_lang, context=None):
        self.translation_calls.append((model, res_id, field, source_lang, context))
        archs = self.views[res_id]
        source_terms = terms.extract_terms(archs[source_lang])
        for lang, pairs in translations.items():
            current = dict(zip(source_terms, terms.extract_terms(archs[lang])))
            mapping = {**current, **pairs}
            archs[lang] = fx.translate_arch(archs[source_lang], mapping.get)
        return True


class RebuildEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.arch_root = self.dir / "estructura"
        self.arch_root.mkdir()
        self.backup = self.dir / "backup_portadas.jsonl"
        self.csv = self.dir / "cambios_portadas.csv"
        self.reference = fx.reference_archs()
        self.before = fx.deviating_archs()
        self.after, self.omitted, _ = rb.rebuild_archs(self.reference, self.before, CID, fx.SITE["slug"])
        (self.arch_root / f"arch_after_{VIEW}.json").write_text(json.dumps(self.after, ensure_ascii=False), encoding="utf-8")
        self.client = TermAwareClient(langs=list(fx.LANGS), websites={SITE: CID}, pages={SITE: VIEW},
                                      companies={CID: {}}, views={VIEW: dict(self.before)})
        self.patcher = mock.patch.object(lib, "client_from_args", lambda args: self.client)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def write_csv(self, rows):
        with open(self.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh, quoting=csv.QUOTE_ALL)
            writer.writerow(lib.CSV_COLUMNS)
            for site, campo, prev, new in rows:
                writer.writerow([site, campo, prev, new, "1.00", "normalize"])

    def run_main(self, *extra):
        out = io.StringIO()
        argv = ["--db", "test", "--csv", str(self.csv), "--arch-root", str(self.arch_root), *extra]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = aplicar.main(argv)
        return code, out.getvalue()

    def rows(self):
        return [(SITE, CAMPO, rb.section_list(self.before["es_ES"]), f"arch_after_{VIEW}.json")]

    def test_parse_campo(self):
        target = lib.parse_campo(CAMPO)
        self.assertEqual((target.kind, target.section, target.view_id, target.model),
                         (lib.KIND_VIEW_REBUILD, "Homepage", VIEW, lib.MODEL_VIEW))
        with self.assertRaises(lib.CampoError):
            lib.parse_campo(f"ir_ui_view.{VIEW}.Hero.rebuild")

    def test_offline_validation(self):
        self.write_csv(self.rows())
        code, out = self.run_main("--offline")
        self.assertEqual(code, 0, out)
        self.assertIn("PLAN", out)
        self.assertEqual(self.client.writes, [])
        # bad file name, escaping path, misaligned languages
        self.write_csv([(SITE, CAMPO, "x", "../arch_after_1.json")])
        self.assertEqual(self.run_main("--offline")[0], 1)
        self.write_csv([(SITE, CAMPO, "x", "arch_before_1.json")])
        self.assertIn("arch_after_<view_id>.json", self.run_main("--offline")[1])
        broken = dict(self.after, de_DE=self.after["de_DE"].replace('<p class="text-muted">', '<p class="text-muted">Extra ', 1))
        (self.arch_root / f"arch_after_{VIEW}.json").write_text(json.dumps(broken), encoding="utf-8")
        self.write_csv(self.rows())
        code, out = self.run_main("--offline")
        self.assertEqual(code, 1)
        self.assertIn("terms", out)

    def test_rebuild_row_is_exclusive_on_its_view(self):
        self.write_csv(self.rows() + [(SITE, f"ir_ui_view.{VIEW}.SEC1.h2", "Tienda de surf en Guanarteme.", "Otra")])
        code, out = self.run_main("--offline")
        self.assertEqual(code, 1)
        self.assertIn("cannot be combined with other rows of the same view", out)

    def test_backup_file_rule(self):
        self.write_csv(self.rows())
        args = aplicar.build_parser().parse_args(["--csv", str(self.csv), "--db", "test"])
        changes, invalid = lib.load_changes(self.csv)
        self.assertEqual(aplicar.resolve_backup(args, changes, invalid), "")
        self.assertEqual(args.backup, lib.REBUILD_BACKUP)
        for reserved in (lib.DEFAULT_BACKUP, lib.S2_BACKUP):
            args.backup = reserved
            self.assertIn("refusing", aplicar.resolve_backup(args, changes, invalid))
        self.write_csv(self.rows() + [(SITE, "res_company.microsite_banner_title", "", "Hola")])
        changes, invalid = lib.load_changes(self.csv)
        args.backup = None
        self.assertIn("strip-2", aplicar.resolve_backup(args, changes, invalid))

    def test_dry_run_connected_writes_nothing(self):
        self.write_csv(self.rows())
        code, out = self.run_main("--backup", str(self.backup))
        self.assertEqual(code, 0, out)
        self.assertIn("WOULD APPLY", out)
        self.assertIn("3 languages, 2 with term translations", out)
        self.assertEqual(self.client.writes, [])
        self.assertFalse(self.backup.exists())

    def test_apply_reproduces_the_proposal_in_every_language(self):
        self.write_csv(self.rows())
        code, out = self.run_main("--apply", "--backup", str(self.backup))
        self.assertEqual(code, 0, out)
        self.assertIn("APPLIED", out)
        self.assertEqual(self.client.writes, [(lib.MODEL_VIEW, VIEW, lib.FIELD_ARCH, "es_ES")])
        self.assertEqual(self.client.contexts[-1], {"lang": "es_ES", "auto_translate_skip": True})
        self.assertEqual(self.client.translation_calls,
                         [(lib.MODEL_VIEW, VIEW, lib.FIELD_ARCH, "es_ES", {"lang": "es_ES", "auto_translate_skip": True})])
        for lang in fx.LANGS:
            self.assertEqual(self.client.views[VIEW][lang], self.after[lang], lang)
        records = lib.read_backup(self.backup)
        events = [r["event"] for r in records]
        self.assertEqual(events, ["backup", "pending", "applied"])
        self.assertEqual(records[0]["valor_anterior"], self.before)
        self.assertIsNone(records[0]["lang"])
        self.assertEqual(records[0]["rows"][0]["campo"], CAMPO)
        # second run: already applied
        code, out = self.run_main("--apply", "--backup", str(self.backup))
        self.assertEqual(code, 0, out)
        self.assertIn("already applied", out)
        self.assertEqual(len(self.client.writes), 1)

    def test_without_translations_the_new_terms_would_read_spanish(self):
        """What the second RPC fixes: the fake client's write alone leaves
        the German page with Spanish Horario labels."""
        self.client.write(lib.MODEL_VIEW, [VIEW], {lib.FIELD_ARCH: self.after["es_ES"]}, {"lang": "es_ES"})
        self.assertIn("Horario", self.client.views[VIEW]["de_DE"])
        self.assertIn("Über uns", self.client.views[VIEW]["de_DE"])   # carried-over term kept

    def test_drift_skips_unless_forced(self):
        self.client.views[VIEW]["es_ES"] = lib.replace_section_h2(self.before["es_ES"], "SEC1", "Texto nuevo")
        self.write_csv(self.rows())
        code, out = self.run_main("--apply", "--backup", str(self.backup))
        self.assertIn("texts changed on server since analysis: sec1", out)
        self.assertEqual(self.client.writes, [])
        self.client.views[VIEW]["es_ES"] = rb._remove_section(self.before["es_ES"], "SEC1")
        code, out = self.run_main("--apply", "--backup", str(self.backup))
        self.assertIn("changed on server since analysis (sections now", out)
        code, out = self.run_main("--apply", "--backup", str(self.backup), "--force", "--only-site", str(SITE))
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.client.writes), 1)

    def test_language_mismatch_with_server_fails(self):
        partial = {lang: arch for lang, arch in self.after.items() if lang != "de_DE"}
        (self.arch_root / f"arch_after_{VIEW}.json").write_text(json.dumps(partial), encoding="utf-8")
        self.write_csv(self.rows())
        code, out = self.run_main("--backup", str(self.backup))
        self.assertEqual(code, 1)
        self.assertIn("differ from the server languages", out)

    def test_translation_failure_is_reported(self):
        def boom(*args, **kwargs):
            raise lib.OdooError("update_field_translations: simulated")
        self.client.update_field_translations = boom
        self.write_csv(self.rows())
        code, out = self.run_main("--apply", "--backup", str(self.backup))
        self.assertEqual(code, 1)
        self.assertIn("es_ES arch written but the translations failed", out)
        self.assertEqual([r["event"] for r in lib.read_backup(self.backup)], ["backup", "pending"])


class PlanUnitTests(unittest.TestCase):
    def test_plan_reports_done_and_notes(self):
        reference, before = fx.reference_archs(), fx.deviating_archs()
        after, _, _ = rb.rebuild_archs(reference, before, CID, "areasurf")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / f"arch_after_{VIEW}.json").write_text(json.dumps(after), encoding="utf-8")
            change = lib.Change(SITE, CAMPO, rb.section_list(before["es_ES"]), f"arch_after_{VIEW}.json", 1.0, "m",
                                lib.parse_campo(CAMPO), 1)
            plan = rebuild.plan_rebuild(change, [change], root, lambda: after, "es_ES", list(fx.LANGS))
            self.assertTrue(plan.done)
            plan = rebuild.plan_rebuild(change, [change], root, lambda: before, "es_ES", list(fx.LANGS))
            self.assertFalse(plan.done or plan.error or plan.drift)
            self.assertEqual(sorted(plan.mapping), ["de_DE", "en_US"])
            self.assertIn("Hero>SEC1>Acerca>Formulario>Subvenciones -> Hero>Horario>SEC1>Acerca>Separador>Formulario>Subvenciones",
                          plan.note)


if __name__ == "__main__":
    unittest.main()
