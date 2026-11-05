"""Recovery paths of ``Homepage.rebuild``: a failed second RPC or a read-back
mismatch leaves ``pending`` without ``applied`` (``revertir.py`` restores the
view from it), ``--force --only-site`` retries to the proposal, and
``--stop-on-error`` stops after the failed view."""
from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jev_apply_lib as lib  # noqa: E402
import rebuild_fixtures as fx  # noqa: E402
import revertir  # noqa: E402
import test_jev_apply_lib as shared  # noqa: E402
from test_aplicar_rebuild import CAMPO, CID, SITE, VIEW, RebuildCase  # noqa: E402

VIEW2, SITE2 = 3718, 218


def boom(*_args, **_kwargs):
    raise lib.OdooError("update_field_translations: simulated")


class RecoveryTests(RebuildCase):
    def fail_translations(self):
        self.original_update = self.client.update_field_translations
        self.client.update_field_translations = boom

    def run_revertir(self, *extra):
        out = io.StringIO()
        done = subprocess.CompletedProcess([], 0, "", "")
        argv = ["--db", "test", "--backup", str(self.backup), "--container", "ctr", "--pg-db", "testdb", *extra]
        with mock.patch.object(revertir.subprocess, "run", return_value=done) as run, \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = revertir.main(argv)
        return code, out.getvalue(), run

    def test_translation_failure_leaves_pending_only(self):
        self.fail_translations()
        self.write_csv(self.rows())
        code, out = self.run_main("--apply", "--backup", str(self.backup))
        self.assertEqual(code, 1)
        self.assertIn("es_ES arch written but the translations failed", out)
        self.assertIn("FAIL", out)
        self.assertEqual(self.events(), ["backup", "pending"])
        self.assertEqual(self.client.views[VIEW]["es_ES"], self.after["es_ES"])
        self.assertNotEqual(self.client.views[VIEW]["de_DE"], self.after["de_DE"])

    def test_readback_mismatch_fails_and_keeps_pending(self):
        real = self.client.update_field_translations

        def dropping(model, res_id, field, translations, source_lang, context=None):
            # Odoo ignores a key that misses a stored term: one pair silently lost.
            trimmed = {lang: {s: t for s, t in pairs.items() if s != "Horario"} for lang, pairs in translations.items()}
            return real(model, res_id, field, trimmed, source_lang, context)
        self.client.update_field_translations = dropping
        self.write_csv(self.rows())
        code, out = self.run_main("--apply", "--backup", str(self.backup))
        self.assertEqual(code, 1)
        self.assertIn("read-back after the write differs from the proposal in de_DE, en_US", out)
        self.assertIn("restore it with revertir.py", out)
        self.assertEqual(self.events(), ["backup", "pending"])
        self.assertEqual(out.count("APPLIED"), 0)

    def test_retry_with_force_reaches_the_proposal(self):
        self.fail_translations()
        self.write_csv(self.rows())
        self.assertEqual(self.run_main("--apply", "--backup", str(self.backup))[0], 1)
        # a plain re-run sees the half-written page as drift
        code, out = self.run_main("--apply", "--backup", str(self.backup))
        self.assertIn("changed on server since analysis", out)
        self.client.update_field_translations = self.original_update
        code, out = self.run_main("--apply", "--backup", str(self.backup), "--force", "--only-site", str(SITE))
        self.assertEqual(code, 0, out)
        self.assertIn("APPLIED", out)
        for lang in fx.LANGS:
            self.assertEqual(self.client.views[VIEW][lang], self.after[lang], lang)
        self.assertEqual(self.events(), ["backup", "pending", "backup", "pending", "applied"])

    def test_revertir_restores_all_languages_from_the_pending_line(self):
        self.fail_translations()
        self.write_csv(self.rows())
        self.assertEqual(self.run_main("--apply", "--backup", str(self.backup))[0], 1)
        code, out, run = self.run_revertir()
        self.assertEqual(code, 0, out)
        run.assert_not_called()
        self.assertIn("WOULD RESTORE", out)
        code, out, run = self.run_revertir("--apply")
        self.assertEqual(code, 0, out)
        run.assert_called_once()
        script = run.call_args.kwargs["input"]
        self.assertEqual(shared._parse_updates(script), {VIEW: self.before})
        self.assertEqual(set(shared._parse_updates(script)[VIEW]), set(fx.LANGS))
        self.assertIn("restored 1 view(s) in one transaction", out)

    def test_stop_on_error_stops_after_the_failed_view(self):
        second_before = {lang: arch.replace("areasurf", "otrosite") for lang, arch in self.before.items()}
        second_after = {lang: arch.replace("areasurf", "otrosite") for lang, arch in self.after.items()}
        self.write_proposal(VIEW2, second_after)
        self.client.websites[SITE2], self.client.pages[SITE2] = CID, VIEW2
        self.client.views[VIEW2] = dict(second_before)
        real = self.client.update_field_translations

        def first_fails(model, res_id, field, translations, source_lang, context=None):
            if res_id == VIEW:
                boom()
            return real(model, res_id, field, translations, source_lang, context)
        self.client.update_field_translations = first_fails
        rows = self.rows() + [(SITE2, f"ir_ui_view.{VIEW2}.Homepage.rebuild", self.rows()[0][2], f"arch_after_{VIEW2}.json")]
        self.write_csv(rows)
        code, out = self.run_main("--apply", "--backup", str(self.backup), "--stop-on-error")
        self.assertEqual(code, 1)
        self.assertIn("stopped on error", out)
        self.assertEqual([w[1] for w in self.client.writes], [VIEW])
        self.assertEqual(self.client.views[VIEW2], second_before)
        self.assertEqual(self.events(), ["backup", "backup", "pending"])
        # without the flag the second view is written and verified
        self.client.views[VIEW] = dict(self.before)
        code, out = self.run_main("--apply", "--backup", str(self.backup))
        self.assertEqual(code, 1)
        self.assertEqual([w[1] for w in self.client.writes], [VIEW, VIEW, VIEW2])
        self.assertEqual(self.client.views[VIEW2], second_after)
        self.assertEqual(out.count("APPLIED"), 1)


if __name__ == "__main__":
    unittest.main()
