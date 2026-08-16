# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install")
class TestMicrositeContentEditor(TransactionCase):
    """A merchant editing the content of their own page, and only their own.

    Reported on 2026-08-16: "el tema de que los contactos no tengan el espacio
    de la pestaña para añadir su contenido de página no está […] creo que va a
    ser mejor colocarlo en sitio web en las pestañas de configuración".

    The screen has to do two things that the company form could not: save at
    all for somebody who is not an administrator, and refuse to save anything
    but the page.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.shop = cls.env["res.company"].create({"name": "Mi Comercio"})
        cls.shop.website_id = cls.env["website"].create(
            {"name": "Mi Comercio", "company_id": cls.shop.id}
        )
        cls.neighbour = cls.env["res.company"].create({"name": "El de al lado"})
        cls.neighbour.website_id = cls.env["website"].create(
            {"name": "El de al lado", "company_id": cls.neighbour.id}
        )
        cls.merchant = new_test_user(
            cls.env,
            login="microsite_merchant",
            groups="base.group_user,website.group_website_restricted_editor",
            company_id=cls.shop.id,
            company_ids=[(6, 0, (cls.shop | cls.neighbour).ids)],
            context={"no_reset_password": True, "tracking_disable": True},
        )

    def _editor(self, user=None):
        return self.env["microsite.content.editor"].with_user(user or self.merchant)

    def test_the_screen_opens_on_the_merchants_own_shop(self):
        values = self._editor().default_get(["company_id", "microsite_about_title"])
        self.assertEqual(values["company_id"], self.shop.id)

    def test_it_opens_filled_in_with_what_is_already_published(self):
        self.shop.sudo().microsite_about_title = "Nuestra historia"
        values = self._editor().default_get(["microsite_about_title"])
        self.assertEqual(values["microsite_about_title"], "Nuestra historia")

    def test_a_merchant_can_actually_save(self):
        """The whole point.

        `res.company` is writable by `base.group_erp_manager` alone, so the
        company form loads for a merchant and then refuses to save. If this
        test ever fails with an AccessError, the screen has been quietly
        turned back into that.
        """
        editor = self._editor().create(
            {
                "microsite_about_title": "Quiénes somos",
                "microsite_opening_hours": "L-V 10:00-14:00",
            }
        )
        editor.action_save()
        self.assertEqual(self.shop.microsite_about_title, "Quiénes somos")
        self.assertEqual(self.shop.microsite_opening_hours, "L-V 10:00-14:00")

    def test_the_shop_being_written_never_comes_off_the_form(self):
        """A company id that came back from a browser is a request, not a fact.

        The neighbour is in this merchant's allowed companies -- that is what
        `zone_company_ownership` does with the zone company -- so pointing the
        form at it is not even far-fetched.
        """
        editor = self._editor().create({"microsite_about_title": "Mío"})
        editor.company_id = self.neighbour
        editor.action_save()
        self.assertEqual(self.shop.microsite_about_title, "Mío")
        self.assertFalse(
            self.neighbour.microsite_about_title,
            "writing had to land on the account's own shop, not on the form's",
        )

    def test_it_writes_the_page_and_nothing_else(self):
        """The VAT number is not part of the page."""
        self.shop.sudo().vat = "ESB00000000"
        editor = self._editor().create({"microsite_about_title": "Hola"})
        editor.action_save()
        self.assertEqual(
            self.shop.vat,
            "ESB00000000",
            "only the whitelist may be written by this screen",
        )

    def test_the_validation_on_the_company_still_runs(self):
        """sudo skips the access rules. It must not skip the constraints."""
        editor = self._editor().create({"microsite_opening_hours": "no es un horario"})
        with self.assertRaises(Exception):
            editor.action_save()

    def test_an_account_with_no_shop_is_told_so_rather_than_shown_a_traceback(self):
        nobody = new_test_user(
            self.env,
            login="microsite_nobody",
            groups="base.group_user,website.group_website_restricted_editor",
            context={"no_reset_password": True, "tracking_disable": True},
        )
        nobody.company_id = self.env.ref("base.main_company")
        with self.assertRaises(UserError):
            self._editor(nobody).default_get(["company_id"])

    def test_the_way_in_is_where_a_merchant_already_works(self):
        menu = self.env.ref(
            "partner_microsite_manager.menu_own_microsite_content",
            raise_if_not_found=False,
        )
        self.assertTrue(menu, "the screen needs a door a merchant can reach")
        self.assertEqual(
            menu.parent_id, self.env.ref("website.menu_website_configuration")
        )
