# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from lxml import etree

from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install")
class TestPartnerMicrositeButton(TransactionCase):
    """Contacts > shop contact > Microsite (client report 2026-09-16).

    "Los usuarios no pueden editar sus datos desde Contactos > contacto de la
    empresa > Microsite, y además no aparecen todos los campos ordenados como
    lo tenemos en la parte de Sitio web."
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, no_microsite_auto=True))
        cls.shop = cls.env["res.company"].create({"name": "Button Shop"})
        cls.env["website"].create({"name": "Button Shop", "company_id": cls.shop.id})
        cls.stranger = cls.env["res.company"].create({"name": "Button Stranger"})
        cls.env["website"].create(
            {"name": "Button Stranger", "company_id": cls.stranger.id}
        )
        (cls.shop | cls.stranger).invalidate_recordset(["website_id"])
        cls.merchant = new_test_user(
            cls.env,
            login="button_merchant",
            groups="base.group_user,website.group_website_restricted_editor",
            company_id=cls.shop.id,
            company_ids=[(6, 0, cls.shop.ids)],
            context={"no_reset_password": True, "tracking_disable": True},
        )

    def _click(self, partner, user):
        return (
            partner.with_user(user)
            .with_context(allowed_company_ids=user.company_ids.ids)
            .action_open_microsite_company()
        )

    def test_a_merchant_gets_the_content_editor_of_their_own_shop(self):
        action = self._click(self.shop.partner_id, self.merchant)
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "microsite.content.editor")
        self.assertEqual(action["views"], [(False, "form")])
        self.assertEqual(action["context"]["microsite_company_id"], self.shop.id)

    def test_a_merchant_cannot_reach_another_shops_editor(self):
        with self.assertRaises(AccessError):
            self._click(self.stranger.partner_id, self.merchant)

    def test_an_administrator_keeps_the_company_form(self):
        action = self.shop.partner_id.action_open_microsite_company()
        self.assertEqual(action["res_model"], "res.company")
        self.assertEqual(action["res_id"], self.shop.id)
        self.assertEqual(action["views"], [(False, "form")])

    def test_the_company_form_sections_follow_the_editor(self):
        """Same five sections as the editor, in the editor's order.

        Asserted on the page names, not the labels: a database without the
        Spanish terms (the CI) renders the English source strings.
        """
        arch = self.env["res.company"].get_view(view_type="form")["arch"]
        notebook = etree.fromstring(arch).xpath(
            "//page[@name='microsite']//notebook[@name='microsite_sections']"
        )
        self.assertTrue(notebook)
        names = [page.get("name") for page in notebook[0].xpath("./page")]
        expected = ["cover", "practical", "about", "social"]
        if "company_facilities" in self.env.registry._init_modules:
            expected.append("facilities")
        self.assertEqual(names[: len(expected)], expected)

    def test_social_links_show_and_save_what_the_footer_prints(self):
        website = self.shop.website_id
        website.social_facebook = "https://www.facebook.com/site"
        self.shop.social_facebook = "https://www.facebook.com/company"
        self.assertEqual(
            self.shop.microsite_social_facebook, "https://www.facebook.com/site"
        )
        self.shop.microsite_social_facebook = "https://www.facebook.com/new"
        self.assertEqual(website.social_facebook, "https://www.facebook.com/new")
        self.assertEqual(self.shop.social_facebook, "https://www.facebook.com/new")
