# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""The website logo form is server QWeb: a term of es.po is applied only when
its msgid is exactly the term of the view, whitespace included. The first
es.po of that form carried the help text on one line and the form stayed in
English."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTranslations(TransactionCase):
    def test_logo_form_is_translated_to_spanish(self):
        # CI databases only have en_US.
        self.env["res.lang"]._activate_lang("es_ES")
        self.env["ir.module.module"].search(
            [("name", "=", "partner_microsite_manager")]
        )._update_translations("es_ES")
        view = self.env.ref("partner_microsite_manager.view_microsite_logo_form")
        arch = view.with_context(lang="es_ES").arch_db
        self.assertIn("Se muestra en la cabecera de todas las páginas", arch)
        self.assertNotIn("Shown in the header", arch)

    def test_map_link_is_translated_to_spanish(self):
        self.env["res.lang"]._activate_lang("es_ES")
        self.env["ir.module.module"].search(
            [("name", "=", "partner_microsite_manager")]
        )._update_translations("es_ES")
        view = self.env.ref("partner_microsite_manager.microsite_homepage_content")
        self.assertIn("Ver en Google Maps", view.with_context(lang="es_ES").arch_db)
        field = self.env["res.company"]._fields["microsite_map_url"]
        self.assertIn(
            "Pegue cualquier enlace de Google Maps",
            field._description_help(self.env(context={"lang": "es_ES"})),
        )
