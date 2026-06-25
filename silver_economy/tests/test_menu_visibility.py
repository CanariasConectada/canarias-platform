# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""La visibilidad de Silver Economy depende del grupo ``group_silver_user``.

Un usuario interno SIN el grupo (status "No" en su configuración) no debe ver el
menú raíz ni acceder a las encuestas; uno CON el grupo sí.
"""
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install")
class TestMenuVisibility(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.menu = cls.env.ref("silver_economy.menu_silver_economy_root")
        cls.survey = cls.env.ref("silver_economy.silver_economy_master_survey")
        cls.group = cls.env.ref("silver_economy.group_silver_user")
        # Evita el envío/render del correo de bienvenida al crear el usuario.
        no_mail_ctx = {
            "no_reset_password": True,
            "tracking_disable": True,
            "mail_create_nosubscribe": True,
        }
        # Usuario interno "No": solo base.group_user, sin el grupo Silver.
        cls.user_without = new_test_user(
            cls.env, login="silver_no", groups="base.group_user", context=no_mail_ctx
        )
        # Usuario interno "Usuario": con el grupo Silver asignado.
        cls.user_with = new_test_user(
            cls.env,
            login="silver_yes",
            groups="base.group_user,silver_economy.group_silver_user",
            context=no_mail_ctx,
        )

    def _menu_visible_for(self, user):
        # _visible_menu_ids() es la API que usa el web client para decidir qué
        # menús ve el usuario (respeta group_ids y el acceso a la acción).
        visible = self.env["ir.ui.menu"].with_user(user)._visible_menu_ids()
        return self.menu.id in visible

    def test_menu_hidden_without_group(self):
        self.assertFalse(
            self.user_without.has_group("silver_economy.group_silver_user")
        )
        self.assertFalse(self._menu_visible_for(self.user_without))

    def test_menu_visible_with_group(self):
        self.assertTrue(self._menu_visible_for(self.user_with))

    def test_survey_access_gated(self):
        with self.assertRaises(AccessError):
            self.survey.with_user(self.user_without).read(["title"])
        # Con el grupo, la encuesta Silver es legible.
        self.assertTrue(self.survey.with_user(self.user_with).read(["title"]))
