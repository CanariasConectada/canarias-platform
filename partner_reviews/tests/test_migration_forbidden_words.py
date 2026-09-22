# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import importlib.util

from odoo.tests import TransactionCase, tagged
from odoo.tools import sql
from odoo.tools.misc import file_path

from odoo.addons.website_moderation_forbidden_word.models.moderation_forbidden_word import (  # noqa: E501
    normalize_text,
)

MIGRATION = "partner_reviews/migrations/19.0.3.0.0/post-migration.py"
OLD_TABLE = "review_forbidden_word"
OLD_MODEL = "review.forbidden.word"


def _load_migration():
    """The migrations folder is not a package: load the script by path."""
    spec = importlib.util.spec_from_file_location(
        "partner_reviews_migration_19_0_3_0_0", file_path(MIGRATION)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged("post_install", "-at_install")
class TestForbiddenWordsMigration(TransactionCase):
    """Replays the 19.0.3.0.0 post-migration against a throwaway copy of the
    old table, built inside the test transaction (DDL included, so it is
    rolled back with everything else)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The module, not the function: assigning a plain function on the
        # class would turn it into a bound method.
        cls.migration = _load_migration()
        cls.Word = cls.env["moderation.forbidden.word"].with_context(active_test=False)

    def _word(self, name):
        return self.Word.search([("name_normalized", "=", normalize_text(name))])

    def _old_xmlids(self):
        self.env.cr.execute(
            "SELECT count(*) FROM ir_model_data WHERE model = %s", (OLD_MODEL,)
        )
        return self.env.cr.fetchone()[0]

    def _build_old_table(self, rows):
        cr = self.env.cr
        self.assertFalse(sql.table_exists(cr, OLD_TABLE), "old table must be gone")
        cr.execute(
            f"CREATE TABLE {OLD_TABLE} "
            "(id serial PRIMARY KEY, name varchar NOT NULL, active boolean)"
        )
        for index, (name, active) in enumerate(rows, start=1):
            cr.execute(
                f"INSERT INTO {OLD_TABLE} (name, active) VALUES (%s, %s)",
                (name, active),
            )
            cr.execute(
                "INSERT INTO ir_model_data (module, name, model, res_id, noupdate) "
                "VALUES ('partner_reviews', %s, %s, %s, true)",
                (f"test_forbidden_word_{index}", OLD_MODEL, index),
            )

    def test_migration_copies_merges_and_cleans_up(self):
        seeded = self._word("hostia")
        self.assertTrue(seeded.active, "precondition: the seed ships hostia active")
        self._build_old_table(
            [
                ("prtestcustomword", True),  # not in the seed: copied
                ("Hostia", False),  # seeded, archived in the old list
                ("IMBECIL", True),  # normalized collision with the seed
                ("PrTestCustomWord", True),  # collision inside the old list
            ]
        )
        self.assertEqual(self._old_xmlids(), 4)
        before = self.Word.search_count([])

        self.migration.migrate(self.env.cr, "19.0.2.2.1")

        custom = self._word("prtestcustomword")
        self.assertEqual(len(custom), 1, "one copy, the collision is skipped")
        self.assertEqual(custom.name, "prtestcustomword")
        self.assertTrue(custom.active)
        self.assertEqual(custom.note, "Migrated from the merchant reviews list")
        self.assertFalse(seeded.active, "archived flag propagated onto the seed")
        self.assertEqual(len(self._word("imbecil")), 1, "no duplicate created")
        self.assertEqual(self.Word.search_count([]), before + 1)
        self.assertEqual(self._old_xmlids(), 0)
        self.assertFalse(sql.table_exists(self.env.cr, OLD_TABLE))

        # Second call (table gone): a no-op.
        self.migration.migrate(self.env.cr, "19.0.2.2.1")
        self.assertEqual(self.Word.search_count([]), before + 1)
        self.assertEqual(len(self._word("prtestcustomword")), 1)

    def test_migration_is_a_noop_without_the_old_table(self):
        before = self.Word.search_count([])
        self.migration.migrate(self.env.cr, "19.0.2.2.1")
        self.assertEqual(self.Word.search_count([]), before)
        self.assertFalse(sql.table_exists(self.env.cr, OLD_TABLE))

    def test_migration_is_a_noop_on_fresh_install(self):
        """No ``version`` means a fresh install: Odoo would not even call the
        script, and the guard keeps a stray table untouched."""
        self._build_old_table([("prtestfreshword", True)])
        self.migration.migrate(self.env.cr, None)
        self.assertFalse(self._word("prtestfreshword"))
        self.assertTrue(sql.table_exists(self.env.cr, OLD_TABLE))
        self.assertEqual(self._old_xmlids(), 1)
