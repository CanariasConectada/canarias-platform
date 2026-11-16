# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""The notification prompt is server QWeb: a term of es.po is applied only
when its msgid is exactly the term of the view, whitespace included."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTranslations(TransactionCase):
    def test_notification_prompt_is_translated_to_spanish(self):
        # CI databases only have en_US.
        self.env["res.lang"]._activate_lang("es_ES")
        self.env["ir.module.module"].search(
            [("name", "=", "website_pwa_push")]
        )._update_translations("es_ES")
        view = self.env.ref("website_pwa_push.pwa_notify_card")
        arch = view.with_context(lang="es_ES").arch_db
        self.assertIn("Activar notificaciones", arch)
        self.assertIn("Ahora no", arch)
        self.assertNotIn("Not now", arch)
