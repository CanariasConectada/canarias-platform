"""Simulate the two rebuild RPCs with Odoo's real ``xml_translate`` on the
real evidence files (``arch_before_<view>.json`` = current prod jsonb,
``arch_after_<view>.json`` = proposal) of every site in
``normalizar_sitios.csv``: all 7 languages must come out byte-identical to
the proposal. Skipped when the files or the Odoo source tree are absent."""
from __future__ import annotations

import csv
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jev_apply_lib as lib  # noqa: E402
import jev_rebuild_terms as terms  # noqa: E402
import odoo_translate_sim as sim  # noqa: E402

SITES = Path(__file__).resolve().parents[1] / "normalizar_sitios.csv"


class RealFilesSimulationTests(unittest.TestCase):
    def setUp(self):
        self.xml_translate = sim.real_xml_translate()
        if self.xml_translate is None:
            self.skipTest("Odoo source tree not importable")
        if not (lib.DEFAULT_ARCH_ROOT / "arch_before_3218.json").is_file():
            self.skipTest(f"evidence files absent in {lib.DEFAULT_ARCH_ROOT}")
        with open(SITES, newline="", encoding="utf-8") as fh:
            self.sites = list(csv.DictReader(fh))

    def load(self, name):
        return json.loads((lib.DEFAULT_ARCH_ROOT / name).read_text(encoding="utf-8"))

    def test_every_proposal_is_reproduced_in_all_languages(self):
        exact, problems = 0, []
        for row in self.sites:
            view = row["view_id"]
            try:
                before, after = self.load(f"arch_before_{view}.json"), self.load(f"arch_after_{view}.json")
            except FileNotFoundError:
                self.skipTest(f"arch files of view {view} absent")
            self.assertEqual(sorted(after), sorted(before), view)
            self.assertEqual(len(after), 7, view)
            got = sim.apply_rebuild(before, after, self.xml_translate)
            bad = [lang for lang in after if got.get(lang) != after[lang]]
            if bad:
                problems.append(f"{row['slug']} ({view}): {', '.join(bad)}")
            else:
                exact += 1
        self.assertEqual(problems, [], "languages differing from the proposal after the simulated RPCs")
        self.assertEqual(exact, len(self.sites))

    def test_term_port_matches_odoo_on_every_real_arch(self):
        for row in self.sites:
            for name in (f"arch_before_{row['view_id']}.json", f"arch_after_{row['view_id']}.json"):
                for lang, arch in self.load(name).items():
                    self.assertEqual(terms.extract_terms(arch), terms.oracle_terms(arch), f"{name} {lang}")


if __name__ == "__main__":
    unittest.main()
