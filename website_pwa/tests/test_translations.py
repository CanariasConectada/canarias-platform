# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Spanish of the app features, in both places Odoo looks for it.

- The systray entry is OWL: its strings reach the browser only through the
  `#. odoo-javascript` entries of es.po.
- The "Download Canarias Conectada" card is server QWeb: a term of es.po is
  applied only when its msgid is exactly the term of the view, whitespace
  included.
"""

from odoo.tests import TransactionCase, tagged
from odoo.tools.translate import code_translations


@tagged("post_install", "-at_install")
class TestTranslations(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # CI databases only have en_US.
        cls.env["res.lang"]._activate_lang("es_ES")

    def test_systray_strings_are_served_in_spanish(self):
        messages = {
            message["id"]: message["string"]
            for message in code_translations.get_web_translations(
                "website_pwa", "es_ES"
            )["messages"]
        }
        self.assertEqual(
            messages.get("Go to the Canarias Conectada website"),
            "Ir a la web de Canarias Conectada",
        )

    def test_download_card_is_translated_to_spanish(self):
        self.env["ir.module.module"].search(
            [("name", "=", "website_pwa")]
        )._update_translations("es_ES")
        view = self.env.ref("website_pwa.pwa_install_quick_access")
        arch = view.with_context(lang="es_ES").arch_db
        self.assertIn("Descarga Canarias Conectada", arch)
        self.assertIn("Instalar la app", arch)
        self.assertNotIn("Download Canarias Conectada", arch)
