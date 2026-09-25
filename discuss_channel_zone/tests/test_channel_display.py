# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import importlib.util

from odoo.tests import TransactionCase, tagged
from odoo.tools.misc import file_path

from odoo.addons.mail.tools.discuss import Store

MIGRATION = "discuss_channel_zone/migrations/19.0.1.1.0/post-migration.py"

CANARIAS_EN = (
    "Community channel of the whole platform. Open to everyone, visitors included."
)
CANARIAS_ES = (
    "Canal de la comunidad de toda la plataforma. "
    "Abierto a todo el mundo, visitantes incluidos."
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "discuss_channel_zone_19_0_1_1_0_post", file_path(MIGRATION)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged("post_install", "-at_install")
class TestSeededChannelDisplay(TransactionCase):
    """The seeded channels are SHOWN translated; nothing stored is."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Channel = cls.env["discuss.channel"]
        cls.channel_canarias = cls.env.ref("discuss_channel_zone.channel_canarias")
        cls.channel_canarias.write({"description": CANARIAS_EN})
        cls.es_active = bool(cls.env["res.lang"].search_count([("code", "=", "es_ES")]))

    def _store_values(self, channel, lang):
        result = (
            Store().add(channel.with_context(lang=lang), ["name", "description"])
        ).get_result()
        rows = [row for row in result["discuss.channel"] if row["id"] == channel.id]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_columns_are_not_translated(self):
        """No jsonb: renames, search and mentions work on one plain value."""
        self.assertFalse(self.Channel._fields["name"].translate)
        self.assertFalse(self.Channel._fields["description"].translate)
        self.env.cr.execute(
            """
            SELECT column_name, data_type FROM information_schema.columns
             WHERE table_name = 'discuss_channel'
               AND column_name IN ('name', 'description')
            """
        )
        self.assertEqual(
            dict(self.env.cr.fetchall()),
            {"name": "character varying", "description": "text"},
        )

    def test_store_payload_is_translated_for_seeded_channel(self):
        if not self.es_active:
            self.skipTest("es_ES is not installed in this database")
        values = self._store_values(self.channel_canarias, "es_ES")
        self.assertEqual(values["description"], CANARIAS_ES)
        self.assertEqual(values["name"], "Canarias Conectada")
        self.assertEqual(
            self._store_values(self.channel_canarias, "en_US")["description"],
            CANARIAS_EN,
        )
        # What is stored is untouched.
        self.assertEqual(
            self.channel_canarias.with_context(lang="es_ES").description, CANARIAS_EN
        )

    def test_seeded_description_matches_with_legacy_indentation(self):
        """Prod stores the text with the XML indentation of 19.0.1.0.0."""
        if not self.es_active:
            self.skipTest("es_ES is not installed in this database")
        self.channel_canarias.description = (
            "Community channel of the whole platform.\n"
            "                Open to everyone, visitors included."
        )
        values = self._store_values(self.channel_canarias, "es_ES")
        self.assertEqual(values["description"], CANARIAS_ES)

    def test_renamed_seeded_channel_shows_what_was_typed(self):
        self.channel_canarias.write(
            {"name": "DCZ Renamed", "description": "DCZ custom topic"}
        )
        values = self._store_values(self.channel_canarias, "es_ES")
        self.assertEqual(values["name"], "DCZ Renamed")
        self.assertEqual(values["description"], "DCZ custom topic")
        self.assertEqual(
            self.channel_canarias.with_context(lang="es_ES").display_name,
            "DCZ Renamed",
        )

    def test_other_channels_untouched(self):
        channel = self.Channel.create(
            {
                "name": "DCZ Market",
                "channel_type": "channel",
                "description": CANARIAS_EN,
            }
        )
        values = self._store_values(channel, "es_ES")
        self.assertEqual(values["description"], CANARIAS_EN)
        self.assertEqual(channel.with_context(lang="es_ES").display_name, "DCZ Market")
        found = self.Channel.search([("name", "=", "DCZ Market")])
        self.assertEqual(found, channel)

    def test_display_name_of_seeded_channel(self):
        self.assertEqual(
            self.channel_canarias.with_context(lang="es_ES").display_name,
            "Canarias Conectada",
        )

    def test_migration_strips_seeded_indentation_only_when_unedited(self):
        guanarteme = self.env.ref("discuss_channel_zone.channel_guanarteme")
        self.channel_canarias.description = (
            "Community channel of the whole platform.\n"
            "                Open to everyone, visitors included."
        )
        guanarteme.description = "DCZ edited by an administrator"
        self.env.flush_all()
        _load_migration().migrate(self.env.cr, "19.0.1.0.0")
        self.env.invalidate_all()
        self.assertEqual(self.channel_canarias.description, CANARIAS_EN)
        self.assertEqual(guanarteme.description, "DCZ edited by an administrator")
