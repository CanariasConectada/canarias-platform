# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install")
class TestDirectoryCategorySelfService(TransactionCase):
    """The merchant files their own shop in the directory.

    Reported on 2026-08-16 as "las etiquetas del comercio deben estar
    disponible para editar por el usuario", clarified as the directory
    category.

    `/mi-comercio` could already do this and nothing linked to it, so the
    field moves to the screen the merchant now uses. What these tests guard
    is that moving it did not also move -- or worse, re-implement -- the
    checks that make it safe.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Creating a company on this platform trips website_sale_collect's
        # warehouse/company constraint; see the note in the comparator tests.
        # It blocks onboarding a merchant, not just this test.
        cls.startClassPatcher(
            patch.object(
                type(cls.env["delivery.carrier"]),
                "_check_warehouses_have_same_company",
                lambda self: None,
            )
        )
        cls.shop = cls.env["res.company"].create({"name": "Comercio Categoría Test"})
        cls.shop.website_id = cls.env["website"].create(
            {"name": "Comercio Categoría Test", "company_id": cls.shop.id}
        )
        cls.folder = cls.env["res.company.category"].create(
            {"name": "Carpeta Test", "type": "view"}
        )
        cls.hairdresser = cls.env["res.company.category"].create(
            {"name": "Peluquería Test", "type": "normal", "parent_id": cls.folder.id}
        )
        cls.bakery = cls.env["res.company.category"].create(
            {"name": "Panadería Test", "type": "normal", "parent_id": cls.folder.id}
        )
        cls.merchant = new_test_user(
            cls.env,
            login="directory_merchant",
            groups="base.group_user,website.group_website_restricted_editor",
            company_id=cls.shop.id,
            company_ids=[(6, 0, cls.shop.ids)],
            context={"no_reset_password": True, "tracking_disable": True},
        )

    def _editor(self, **values):
        return (
            self.env["microsite.content.editor"].with_user(self.merchant).create(values)
        )

    def test_the_screen_opens_on_the_category_the_shop_already_has(self):
        self.shop.sudo().category_id = self.bakery
        values = (
            self.env["microsite.content.editor"]
            .with_user(self.merchant)
            .default_get(["directory_category_id"])
        )
        self.assertEqual(values["directory_category_id"], self.bakery.id)

    def test_a_merchant_can_file_their_own_shop(self):
        """The whole request.

        Writing category_id on res.company needs Administration rights, which
        no merchant has; if this ever fails with an AccessError the field has
        stopped going through set_own_directory_category.
        """
        self._editor(directory_category_id=self.hairdresser.id).action_save()
        self.assertEqual(self.shop.category_id, self.hairdresser)

    def test_leaving_it_empty_takes_the_shop_out_of_its_category(self):
        self.shop.sudo().category_id = self.bakery
        self._editor(directory_category_id=False).action_save()
        self.assertFalse(self.shop.category_id)

    def test_a_folder_is_still_refused(self):
        """A "view" category groups other categories and counts nothing.

        The domain on the field is a hint the interface honours; this is the
        check that holds when the value arrives some other way.
        """
        with self.assertRaises(UserError):
            self._editor(directory_category_id=self.folder.id).action_save()

    def test_the_page_content_is_saved_in_the_same_sitting(self):
        """One screen, one Save. The category must not cost a second trip."""
        editor = self._editor(
            directory_category_id=self.bakery.id,
            microsite_about_title="Nuestra historia",
        )
        editor.action_save()
        self.assertEqual(self.shop.category_id, self.bakery)
        self.assertEqual(self.shop.microsite_about_title, "Nuestra historia")

    def test_a_rejected_category_does_not_leave_the_page_half_saved(self):
        """Both writes are one transaction, so neither lands alone."""
        editor = self._editor(
            directory_category_id=self.folder.id,
            microsite_about_title="No debería guardarse",
        )
        with self.assertRaises(UserError):
            with self.env.cr.savepoint():
                editor.action_save()
        self.assertNotEqual(self.shop.microsite_about_title, "No debería guardarse")


@tagged("post_install", "-at_install")
class TestDirectoryCategoryMultiShop(TransactionCase):
    """The category follows the PICKED shop, never the session's.

    `partner_microsite_manager` may now open this screen on a shop that is
    NOT the session's own (an owner of several real shops picks one); the
    category write must land on that same picked shop, exactly like the
    page content it is saved alongside.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.startClassPatcher(
            patch.object(
                type(cls.env["delivery.carrier"]),
                "_check_warehouses_have_same_company",
                lambda self: None,
            )
        )
        Company = cls.env["res.company"]
        cls.shop_a = Company.create({"name": "Comercio Multi A"})
        cls.shop_a.website_id = cls.env["website"].create(
            {"name": "Comercio Multi A", "company_id": cls.shop_a.id}
        )
        cls.shop_b = Company.create({"name": "Comercio Multi B"})
        cls.shop_b.website_id = cls.env["website"].create(
            {"name": "Comercio Multi B", "company_id": cls.shop_b.id}
        )
        cls.category = cls.env["res.company.category"].create(
            {"name": "Categoría Multi Test", "type": "normal"}
        )
        cls.owner = new_test_user(
            cls.env,
            login="directory_multi_owner",
            groups="base.group_user,website.group_website_restricted_editor",
            company_id=cls.shop_a.id,
            company_ids=[(6, 0, (cls.shop_a | cls.shop_b).ids)],
            context={"no_reset_password": True, "tracking_disable": True},
        )

    def test_the_category_lands_on_the_picked_shop_not_the_session_shop(self):
        editor = (
            self.env["microsite.content.editor"]
            .with_user(self.owner)
            .with_context(microsite_company_id=self.shop_b.id)
            .create({"directory_category_id": self.category.id})
        )
        editor.action_save()
        self.assertEqual(self.shop_b.category_id, self.category)
        self.assertFalse(self.shop_a.category_id)
