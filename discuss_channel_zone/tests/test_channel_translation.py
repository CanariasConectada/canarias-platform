# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import importlib.util

from odoo.tests import TransactionCase, tagged
from odoo.tools.misc import file_path

MIGRATION = "discuss_channel_zone/migrations/19.0.1.1.0/post-migration.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "discuss_channel_zone_19_0_1_1_0_post", file_path(MIGRATION)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged("post_install", "-at_install")
class TestChannelTranslation(TransactionCase):
    """Channel names and descriptions are translated fields."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Channel = cls.env["discuss.channel"]
        cls.channel_canarias = cls.env.ref("discuss_channel_zone.channel_canarias")
        cls.es_active = bool(cls.env["res.lang"].search_count([("code", "=", "es_ES")]))

    def _raw(self, channel, column):
        self.env.flush_all()
        self.env.cr.execute(
            f"SELECT {column} FROM discuss_channel WHERE id = %s", (channel.id,)
        )
        return self.env.cr.fetchone()[0]

    def test_fields_are_translatable_and_stored_as_jsonb(self):
        self.assertTrue(self.Channel._fields["name"].translate)
        self.assertTrue(self.Channel._fields["description"].translate)
        self.assertIsInstance(self._raw(self.channel_canarias, "name"), dict)

    def test_seeded_channel_is_translated_in_spanish(self):
        if not self.es_active:
            self.skipTest("es_ES is not installed in this database")
        channel = self.channel_canarias.with_context(lang="es_ES")
        self.assertEqual(
            channel.description,
            "Canal de la comunidad de toda la plataforma. "
            "Abierto a todo el mundo, visitantes incluidos.",
        )
        self.assertEqual(
            self.channel_canarias.with_context(lang="en_US").description,
            "Community channel of the whole platform. "
            "Open to everyone, visitors included.",
        )

    def test_rename_in_one_language_keeps_the_others(self):
        if not self.es_active:
            self.skipTest("es_ES is not installed in this database")
        channel = self.Channel.with_context(lang="en_US").create(
            {"name": "DCZ Market", "channel_type": "channel"}
        )
        channel.with_context(lang="es_ES").name = "DCZ Mercado"
        self.assertEqual(channel.with_context(lang="en_US").name, "DCZ Market")
        self.assertEqual(channel.with_context(lang="es_ES").name, "DCZ Mercado")
        found = self.Channel.with_context(lang="es_ES").search(
            [("name", "=", "DCZ Mercado")]
        )
        self.assertEqual(found, channel)

    def test_migration_copies_spanish_and_cleans_seeded_descriptions(self):
        """19.0.1.1.0 post-migration, on the shapes the upgrade leaves behind."""
        channel = self.Channel.with_context(lang="en_US").create(
            {"name": "DCZ Legacy", "channel_type": "channel"}
        )
        self.env.flush_all()
        self.env.cr.execute(
            """
            UPDATE discuss_channel SET name = jsonb_build_object('en_US', 'DCZ Legacy')
             WHERE id = %s
            """,
            (channel.id,),
        )
        indented = (
            "Community channel of the whole platform.\n"
            "                Open to everyone, visitors included."
        )
        self.env.cr.execute(
            """
            UPDATE discuss_channel
               SET description = description || jsonb_build_object('en_US', %s)
             WHERE id = %s
            """,
            (indented, self.channel_canarias.id),
        )
        _load_migration().migrate(self.env.cr, "19.0.1.0.0")
        self.env.invalidate_all()

        self.assertEqual(
            self._raw(channel, "name"), {"en_US": "DCZ Legacy", "es_ES": "DCZ Legacy"}
        )
        self.assertEqual(
            self._raw(self.channel_canarias, "description")["en_US"],
            "Community channel of the whole platform. "
            "Open to everyone, visitors included.",
        )
        # Seeded channels take their Spanish from the .po files, never from a
        # copy of the English text.
        if self.es_active:
            self.assertNotEqual(
                self._raw(self.channel_canarias, "description")["es_ES"],
                self._raw(self.channel_canarias, "description")["en_US"],
            )
