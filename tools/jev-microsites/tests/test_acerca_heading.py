"""``Acerca.h6_1`` / ``Acerca.h6_2``: rewrite the ``<h6>`` heading of an
existing Acerca column, compared like ``.h1`` and written in the primary
language only."""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))   # test_jev_apply_lib under pytest too
import aplicar  # noqa: E402
import jev_apply_lib as lib  # noqa: E402
import test_jev_apply_lib as shared  # noqa: E402  (FakeClient and the legacy arch fixtures)

LEGACY_TWO = shared.LEGACY_TWO          # col1 "Nuestra historia", col2 "Nuestros servicios"
LEGACY_ONE = shared.LEGACY_ONE          # col1 only
SPLICED = LEGACY_TWO.replace("Nuestra historia", "Sobre nosotrTexto largo pegado por error.os")
NO_H6 = LEGACY_TWO.replace('<h6 class="text-center">Nuestra historia</h6>', "")


class HeadingLibTests(unittest.TestCase):
    def test_extract(self):
        self.assertEqual(lib.extract_acerca_heading(LEGACY_TWO, 1), "Nuestra historia")
        self.assertEqual(lib.extract_acerca_heading(LEGACY_TWO, 2), "Nuestros servicios")
        self.assertEqual(lib.extract_acerca_heading(SPLICED, 1), "Sobre nosotrTexto largo pegado por error.os")
        self.assertIsNone(lib.extract_acerca_heading(LEGACY_ONE, 2))
        self.assertIsNone(lib.extract_acerca_heading(NO_H6, 1))
        with self.assertRaises(lib.SectionNotFound):
            lib.extract_acerca_heading("<div/>", 1)

    def test_extract_normalises_whitespace_entities_and_tags(self):
        arch = LEGACY_TWO.replace("Nuestra historia", "  Pan &amp;\n <b>vino</b> ")
        self.assertEqual(lib.extract_acerca_heading(arch, 1), "Pan & vino")

    def test_replace_keeps_attributes_and_everything_else(self):
        out = lib.replace_acerca_heading(SPLICED, 1, "Sobre nosotros")
        self.assertIn('<h6 class="text-center">Sobre nosotros</h6>', out)
        self.assertEqual(out, LEGACY_TWO.replace("Nuestra historia", "Sobre nosotros"))
        self.assertEqual(lib.extract_acerca_heading(out, 1), "Sobre nosotros")
        self.assertEqual(lib.extract_acerca_heading(out, 2), "Nuestros servicios")
        # the column texts are untouched
        self.assertEqual(lib.extract_acerca_column(out, 1), "Historia completa")

    def test_replace_column_2_escapes(self):
        out = lib.replace_acerca_heading(LEGACY_TWO, 2, "Servicios & <más>")
        self.assertIn('<h6 class="text-center">Servicios &amp; &lt;más&gt;</h6>', out)
        self.assertIn('<h6 class="text-center">Nuestra historia</h6>', out)

    def test_replace_identifies_slot_by_id_not_position(self):
        swapped = shared._legacy_arch(shared.COL2 + "\n" + shared.COL1)
        out = lib.replace_acerca_heading(swapped, 1, "Historia")
        self.assertEqual(lib.extract_acerca_heading(out, 1), "Historia")
        self.assertEqual(lib.extract_acerca_heading(out, 2), "Nuestros servicios")

    def test_replace_never_creates_and_rejects_bad_input(self):
        with self.assertRaisesRegex(lib.ArchError, "missing"):
            lib.replace_acerca_heading(LEGACY_ONE, 2, "x")
        with self.assertRaisesRegex(lib.ArchError, "no <h6>"):
            lib.replace_acerca_heading(NO_H6, 1, "x")
        with self.assertRaisesRegex(lib.ArchError, "unsupported"):
            lib.replace_acerca_heading(LEGACY_TWO, 3, "x")
        with self.assertRaisesRegex(lib.ArchError, "empty"):
            lib.replace_acerca_heading(LEGACY_TWO, 1, "  ")
        with self.assertRaises(lib.SectionNotFound):
            lib.replace_acerca_heading("<div/>", 1, "x")


class HeadingParseTests(unittest.TestCase):
    def test_parse(self):
        t = lib.parse_campo("ir_ui_view.3929.Acerca.h6_1")
        self.assertEqual((t.kind, t.view_id, t.section, t.column, t.field),
                         (lib.KIND_VIEW_H6, 3929, "Acerca", 1, "arch_db"))
        self.assertEqual(lib.parse_campo("ir_ui_view.4005.Acerca.h6_2").column, 2)
        self.assertIn("h6_1", lib.ACERCA_OPS)
        self.assertIn("h6_2", lib.ACERCA_OPS)

    def test_invalid(self):
        for bad in ("ir_ui_view.1.Acerca.h6_3", "ir_ui_view.1.Acerca.h6_", "ir_ui_view.1.Acerca.h6",
                    "ir_ui_view.1.Hero.h6_1", "ir_ui_view.1.SEC1.h6_2", "ir_ui_view.1.Acerca.h6_01x"):
            with self.assertRaises(lib.CampoError, msg=bad):
                lib.parse_campo(bad)

    def test_processing_order_headings_after_inserts_and_columns(self):
        def row(campo, line):
            return lib.Change(68, campo, "", "", 1.0, "", lib.parse_campo(campo), line)
        rows = [row("ir_ui_view.1.Acerca.h6_2", 1), row("ir_ui_view.1.Hero.bg", 2), row("ir_ui_view.1.Acerca.col2", 3),
                row("ir_ui_view.1.Acerca.insert", 4), row("ir_ui_view.1.Acerca.h6_1", 5)]
        ordered = [c.campo for c in lib.group_by_site(rows)[68]]
        self.assertEqual(ordered, ["ir_ui_view.1.Acerca.insert", "ir_ui_view.1.Acerca.col2",
                                   "ir_ui_view.1.Acerca.h6_2", "ir_ui_view.1.Acerca.h6_1", "ir_ui_view.1.Hero.bg"])


class HeadingApplyTests(unittest.TestCase):
    """End to end on the in-memory client (dry-run, apply, skips, offline)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.zip_root = self.dir / "zip"
        self.zip_root.mkdir()
        self.backup = self.dir / "backup.jsonl"
        self.csv = self.dir / "cambios.csv"
        self.client = shared.FakeClient(
            langs=["en_US", "es_ES"], websites={158: 158}, pages={158: 3929},
            companies={158: {}},
            views={3929: {"es_ES": SPLICED, "en_US": SPLICED.replace("Nuestros servicios", "Our services")}},
        )
        self.patcher = mock.patch.object(lib, "client_from_args", lambda args: self.client)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def write_csv(self, rows):
        lines = [shared.CSV_HEADER]
        for site, campo, prev, new in rows:
            lines.append(f'"{site}","{campo}","{prev}","{new}","1.00","m"\n')
        self.csv.write_text("".join(lines), encoding="utf-8")

    def run_main(self, *extra):
        out = io.StringIO()
        argv = ["--db", "test", "--csv", str(self.csv), "--zip-root", str(self.zip_root),
                "--backup", str(self.backup), *extra]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = aplicar.main(argv)
        return code, out.getvalue()

    ROW = (158, "ir_ui_view.3929.Acerca.h6_1", "Sobre nosotrTexto largo pegado por error.os", "Sobre nosotros")

    def test_dry_run_shows_current_and_writes_nothing(self):
        self.write_csv([self.ROW])
        code, out = self.run_main()
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"Acerca\.h6_1\s+WOULD APPLY.*current='Sobre nosotrTexto.*new='Sobre nosotros'")
        self.assertEqual(self.client.writes, [])
        self.assertFalse(self.backup.exists())

    def test_apply_writes_primary_language_only_and_is_idempotent(self):
        self.write_csv([self.ROW, (158, "ir_ui_view.3929.Acerca.h6_2", "Nuestros servicios", "Qué ofrecemos")])
        code, out = self.run_main("--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("APPLIED"), 2)
        # one arch write, es_ES context, both headings in it (like .h1)
        self.assertEqual(self.client.writes, [("ir.ui.view", 3929, "arch_db", "es_ES")])
        self.assertEqual(self.client.contexts, [{"lang": "es_ES"}])
        es = self.client.views[3929]["es_ES"]
        self.assertEqual(lib.extract_acerca_heading(es, 1), "Sobre nosotros")
        self.assertEqual(lib.extract_acerca_heading(es, 2), "Qué ofrecemos")
        self.assertEqual(es, LEGACY_TWO.replace("Nuestra historia", "Sobre nosotros")
                         .replace("Nuestros servicios", "Qué ofrecemos"))
        # backup holds every language of the view
        backup_line = [l for l in self.backup.read_text().splitlines() if '"backup"' in l]
        self.assertEqual(len(backup_line), 1)
        self.assertIn('"en_US"', backup_line[0])
        code, out = self.run_main("--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("already applied"), 2)
        self.assertEqual(len(self.client.writes), 1)

    def test_mismatch_is_skipped(self):
        self.write_csv([(158, "ir_ui_view.3929.Acerca.h6_1", "Sobre nosotros", "Quiénes somos")])
        code, out = self.run_main("--apply")
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"Acerca\.h6_1\s+SKIP.*changed on server")
        self.assertEqual(self.client.writes, [])
        self.assertEqual(lib.extract_acerca_heading(self.client.views[3929]["es_ES"], 1),
                         "Sobre nosotrTexto largo pegado por error.os")

    def test_mismatch_compares_normalised(self):
        self.write_csv([(158, "ir_ui_view.3929.Acerca.h6_1", "  Sobre nosotrTexto largo\n pegado por error.os ",
                         "Sobre nosotros")])
        code, out = self.run_main("--apply")
        self.assertEqual(code, 0, out)
        self.assertIn("APPLIED", out)

    def test_missing_column_or_section_fails_without_creating(self):
        self.client.views[3929] = {"es_ES": LEGACY_ONE, "en_US": LEGACY_ONE}
        self.write_csv([(158, "ir_ui_view.3929.Acerca.h6_2", "Nuestros servicios", "Qué ofrecemos")])
        code, out = self.run_main("--apply")
        self.assertEqual(code, 1, out)
        self.assertRegex(out, r"Acerca\.h6_2\s+FAIL.*column 2 or its <h6> not found")
        self.assertEqual(self.client.writes, [])
        self.client.views[3929] = {"es_ES": shared.NO_ACERCA, "en_US": shared.NO_ACERCA}
        code, out = self.run_main("--apply")
        self.assertRegex(out, r"Acerca\.h6_2\s+FAIL.*section 'Acerca' not found")
        self.assertEqual(self.client.writes, [])

    def test_offline_validation(self):
        self.write_csv([
            self.ROW,
            (173, "ir_ui_view.4005.Acerca.h6_2", "Nuestros serviciios", "Nuestros servicios"),
            (173, "ir_ui_view.4005.Acerca.h6_1", "x", "   "),
        ])
        code, out = self.run_main("--offline")
        self.assertEqual(code, 1)
        self.assertIn("would apply: 2", out)
        self.assertIn("failed:  1", out)
        self.assertRegex(out, r"ir_ui_view\.3929\.Acerca\.h6_1\s+PLAN")
        self.assertRegex(out, r"ir_ui_view\.4005\.Acerca\.h6_2\s+PLAN")
        self.assertRegex(out, r"ir_ui_view\.4005\.Acerca\.h6_1\s+FAIL.*empty text for Acerca\.h6_1")


if __name__ == "__main__":
    unittest.main()
