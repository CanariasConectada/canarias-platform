# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""The banner is an OWL component: its Spanish must reach the browser.

Odoo serves browser translations only from the .po entries flagged
`#. odoo-javascript` (`code_translations.get_web_translations`). An entry
without the flag is loaded for nothing and the banner shows English.
"""

from odoo.tests import TransactionCase, tagged
from odoo.tools.translate import code_translations


@tagged("post_install", "-at_install")
class TestBannerTranslations(TransactionCase):
    def test_banner_strings_are_served_to_the_browser_in_spanish(self):
        # CI databases only have en_US.
        self.env["res.lang"]._activate_lang("es_ES")
        messages = {
            message["id"]: message["string"]
            for message in code_translations.get_web_translations(
                "discuss_community", "es_ES"
            )["messages"]
        }
        self.assertEqual(messages.get("Activate and verify"), "Activar y comprobar")
        self.assertEqual(
            messages.get("Notifications are not active on this device."),
            "Las notificaciones no están activas en este dispositivo.",
        )
        self.assertEqual(messages.get("Hide for now"), "Ocultar por ahora")
