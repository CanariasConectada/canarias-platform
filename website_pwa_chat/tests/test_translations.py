# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""The Discuss support button and name dialog are OWL: their Spanish must
reach the browser through the `#. odoo-javascript` entries of es.po."""

from odoo.tests import TransactionCase, tagged
from odoo.tools.translate import code_translations


@tagged("post_install", "-at_install")
class TestWebTranslations(TransactionCase):
    def test_support_dialog_strings_are_served_in_spanish(self):
        # CI databases only have en_US.
        self.env["res.lang"]._activate_lang("es_ES")
        messages = {
            message["id"]: message["string"]
            for message in code_translations.get_web_translations(
                "website_pwa_chat", "es_ES"
            )["messages"]
        }
        self.assertEqual(messages.get("Request support"), "Solicitar soporte")
        self.assertEqual(messages.get("Who is asking?"), "¿Quién pregunta?")
        self.assertEqual(messages.get("Cancel"), "Cancelar")

    def test_sound_switch_strings_are_served_in_spanish(self):
        """The chat page's message-sound switch is labelled from JS."""
        self.env["res.lang"]._activate_lang("es_ES")
        messages = {
            message["id"]: message["string"]
            for message in code_translations.get_web_translations(
                "website_pwa_chat", "es_ES"
            )["messages"]
        }
        self.assertEqual(
            messages.get("Mute message sound"), "Silenciar el sonido de los mensajes"
        )
        self.assertEqual(
            messages.get("Turn on message sound"), "Activar el sonido de los mensajes"
        )
