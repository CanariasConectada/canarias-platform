# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from lxml import etree

from odoo.exceptions import AccessError
from odoo.tests import Form, tagged
from odoo.tests.common import TransactionCase, new_test_user

from .test_logo_follows_company import PNG_A, PNG_B

USER_CTX = {"no_reset_password": True, "tracking_disable": True}


@tagged("post_install", "-at_install")
class TestWebsiteLogo(TransactionCase):
    """A merchant changes their website logo from Website > Site > Content.

    Client request 2026-09-25: "No hay un espacio en sitio web para cambiar
    el logo del sitio web, por favor, habilítalo para que podamos hacerlo
    desde la parte de contenido de sitio web".
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.shop = cls.env["res.company"].create(
            {"name": "Logo Merchant Shop", "logo": PNG_A}
        )
        cls.site = cls.env["website"].create(
            {"name": "Logo Merchant site", "company_id": cls.shop.id, "logo": PNG_A}
        )
        # A second site of the same shop: the header of both must follow.
        cls.second_site = cls.env["website"].create(
            {
                "name": "Logo Merchant second site",
                "company_id": cls.shop.id,
                "logo": PNG_A,
            }
        )
        cls.shop.website_id = cls.site
        cls.other = cls.env["res.company"].create(
            {"name": "Other Logo Shop", "logo": PNG_A}
        )
        cls.other_site = cls.env["website"].create(
            {"name": "Other Logo site", "company_id": cls.other.id, "logo": PNG_A}
        )
        cls.other.website_id = cls.other_site
        cls.merchant = new_test_user(
            cls.env,
            login="website_logo_merchant",
            groups="base.group_user,website.group_website_restricted_editor",
            company_id=cls.shop.id,
            company_ids=[(6, 0, cls.shop.ids)],
            context=USER_CTX,
        )

    def _editor(self, company=None, user=None):
        return (
            self.env["microsite.content.editor"]
            .with_user(user or self.merchant)
            .with_context(
                allowed_company_ids=self.shop.ids,
                microsite_company_id=(company or self.shop).id,
            )
        )

    def test_a_merchant_changes_the_logo_of_every_site_of_the_shop(self):
        editor = self._editor().create({"company_id": self.shop.id, "logo": PNG_B})
        editor.action_save_logo()
        self.assertEqual(self.shop.logo, PNG_B)
        self.assertEqual(self.site.logo, PNG_B)
        self.assertEqual(self.second_site.logo, PNG_B)
        self.assertEqual(self.other_site.logo, PNG_A)

    def test_the_full_editor_saves_the_logo_too(self):
        values = self._editor().default_get(["company_id", "logo"])
        self.assertEqual(values["logo"], PNG_A)
        editor = self._editor().create(
            dict(
                self._editor().default_get(
                    list(self.env["microsite.content.editor"]._fields)
                ),
                logo=PNG_B,
            )
        )
        editor.action_save()
        self.assertEqual(self.site.logo, PNG_B)

    def test_saving_an_untouched_logo_rewrites_nothing(self):
        # The header shows the website's own logo; the company holds another.
        self.site.logo = PNG_B
        editor = self._editor().create(
            self._editor().default_get(["company_id", "logo"])
        )
        self.assertEqual(editor.logo, PNG_B)
        editor.action_save_logo()
        self.assertEqual(self.shop.logo, PNG_A)
        self.assertEqual(self.second_site.logo, PNG_A)

    def test_an_emptied_logo_is_not_written(self):
        editor = self._editor().create({"company_id": self.shop.id, "logo": False})
        editor.action_save_logo()
        self.assertEqual(self.site.logo, PNG_A)

    def test_a_site_with_odoos_svg_placeholder_still_opens(self):
        """A new website carries Odoo's SVG logo, which core refuses to
        store for anyone but an administrator: the screen falls back to the
        company's logo instead of failing to open."""
        self.site.logo = self.env["website"]._default_logo()
        editor = self._editor().create(
            self._editor().default_get(["company_id", "logo"])
        )
        self.assertEqual(editor.logo, PNG_A)
        self.shop.sudo().partner_id.image_1920 = False
        editor = self._editor().create(
            self._editor().default_get(["company_id", "logo"])
        )
        self.assertFalse(editor.logo)
        editor.action_save_logo()
        self.assertTrue(self.site.logo, "an empty screen must not clear the header")

    def test_a_merchant_cannot_touch_another_shops_logo(self):
        with self.assertRaises(AccessError):
            self._editor(company=self.other).default_get(["company_id", "logo"])
        editor = self._editor().create({"company_id": self.shop.id, "logo": PNG_B})
        # A tampered selector: the stranger's id where the shop's was.
        editor.sudo().company_id = self.other
        with self.assertRaises(AccessError):
            editor.action_save_logo()
        self.assertEqual(self.other.logo, PNG_A)
        self.assertEqual(self.other_site.logo, PNG_A)

    def test_the_menu_is_under_content_and_visible_to_restricted_editors(self):
        menu = self.env.ref("partner_microsite_manager.menu_own_website_logo")
        content = self.env.ref("website.menu_content")
        self.assertEqual(menu.parent_id, content)
        menus = (
            self.env["ir.ui.menu"]
            .with_user(self.merchant)
            .with_context(allowed_company_ids=self.shop.ids)
            .load_menus(debug=False)
        )
        self.assertIn(menu.id, menus)
        self.assertIn(content.id, menus)
        self.assertIn(menu.id, menus[content.id]["children"])
        self.assertIn(content.id, menus[content.parent_id.id]["children"])

    def test_the_menu_opens_the_logo_form_for_a_merchant(self):
        action = self.env.ref("partner_microsite_manager.action_own_website_logo")
        result = (
            action.with_user(self.merchant)
            .with_context(allowed_company_ids=self.shop.ids)
            .run()
        )
        self.assertEqual(result["res_model"], "microsite.content.editor")
        view = self.env.ref("partner_microsite_manager.view_microsite_logo_form")
        self.assertEqual(result["views"], [(view.id, "form")])
        self.assertEqual(result["context"]["microsite_company_id"], self.shop.id)

    def test_the_logo_form_loads_and_saves_for_a_merchant(self):
        view = self.env.ref("partner_microsite_manager.view_microsite_logo_form")
        views = self._editor().get_views([(view.id, "form")])
        arch = etree.fromstring(views["views"]["form"]["arch"])
        self.assertTrue(arch.xpath("//field[@name='logo']"))
        self.assertTrue(arch.xpath("//button[@name='action_save_logo']"))
        with Form(self._editor(), view=view) as form:
            self.assertEqual(form.company_id, self.shop)
            self.assertFalse(form.can_pick_company)
            form.logo = PNG_B
            editor = form.save()
        editor.action_save_logo()
        self.assertEqual(self.site.logo, PNG_B)

    def test_an_owner_of_two_shops_picks_the_shop(self):
        owner = new_test_user(
            self.env,
            login="website_logo_owner_of_two",
            groups="base.group_user,website.group_website_restricted_editor",
            company_id=self.shop.id,
            company_ids=[(6, 0, (self.shop | self.other).ids)],
            context=USER_CTX,
        )
        view = self.env.ref("partner_microsite_manager.view_microsite_logo_form")
        editor_env = (
            self.env["microsite.content.editor"]
            .with_user(owner)
            .with_context(
                allowed_company_ids=(self.shop | self.other).ids,
                microsite_company_id=self.shop.id,
            )
        )
        with Form(editor_env, view=view) as form:
            self.assertTrue(form.can_pick_company)
            form.company_id = self.other
            form.logo = PNG_B
            editor = form.save()
        editor.action_save_logo()
        self.assertEqual(self.other_site.logo, PNG_B)
        self.assertEqual(self.site.logo, PNG_A)
