# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

ARCH = "<div>página de prueba</div>"


@tagged("post_install", "-at_install")
class TestMerchantViewScoping(TransactionCase):
    """A merchant writes the views of THEIR site, and of no other.

    Merchants hold ``website.group_website_restricted_editor`` — it is what
    opens their Page content screen and the frontend Translate mode. Core
    ships no rule about WHICH views that group may write, so before
    ``rule_restricted_editor_own_website_views`` a merchant reaching another
    shop's subdomain could edit that shop's pages.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.shop = cls.env["res.company"].create({"name": "Tienda Regla"})
        cls.shop.website_id = cls.env["website"].create(
            {"name": "Tienda Regla", "company_id": cls.shop.id}
        )
        cls.neighbour = cls.env["res.company"].create({"name": "Vecina Regla"})
        cls.neighbour.website_id = cls.env["website"].create(
            {"name": "Vecina Regla", "company_id": cls.neighbour.id}
        )
        cls.merchant = new_test_user(
            cls.env,
            login="scoping_merchant",
            groups="base.group_user,website.group_website_restricted_editor",
            company_id=cls.shop.id,
            company_ids=[(6, 0, cls.shop.ids)],
            context={"no_reset_password": True, "tracking_disable": True},
        )
        cls.designer = new_test_user(
            cls.env,
            login="scoping_designer",
            groups="base.group_user,website.group_website_designer",
            company_id=cls.shop.id,
            company_ids=[(6, 0, (cls.shop | cls.neighbour).ids)],
            context={"no_reset_password": True, "tracking_disable": True},
        )
        cls.own_view = cls._page_view(cls.shop.website_id, "propia")
        cls.other_view = cls._page_view(cls.neighbour.website_id, "ajena")

    @classmethod
    def _page_view(cls, website, name):
        return cls.env["ir.ui.view"].create(
            {
                "name": name,
                "type": "qweb",
                "arch": ARCH,
                "website_id": website.id,
                "key": "test.scoping_%s" % name,
            }
        )

    def test_a_merchant_edits_their_own_page(self):
        view = self.own_view.with_user(self.merchant)
        view.write({"arch": ARCH.replace("prueba", "editada")})
        self.assertIn("editada", view.arch)

    def test_a_merchant_cannot_edit_the_neighbours_page(self):
        with self.assertRaises(AccessError):
            self.other_view.with_user(self.merchant).write(
                {"arch": ARCH.replace("prueba", "intrusa")}
            )

    def test_a_merchant_cannot_edit_a_master_template(self):
        """No ``website_id`` means every site renders it. Nobody's page."""
        master = self.env["ir.ui.view"].search(
            [("website_id", "=", False), ("type", "=", "qweb")], limit=1
        )
        with self.assertRaises(AccessError):
            master.with_user(self.merchant).write({"name": master.name})

    def test_a_merchant_creates_cow_copies_on_their_own_site_only(self):
        creado = (
            self.env["ir.ui.view"]
            .with_user(self.merchant)
            .create(
                {
                    "name": "cow propia",
                    "type": "qweb",
                    "arch": ARCH,
                    "website_id": self.shop.website_id.id,
                    "key": "test.scoping_cow",
                }
            )
        )
        self.assertTrue(creado.exists())
        with self.assertRaises(AccessError):
            self.env["ir.ui.view"].with_user(self.merchant).create(
                {
                    "name": "cow ajena",
                    "type": "qweb",
                    "arch": ARCH,
                    "website_id": self.neighbour.website_id.id,
                    "key": "test.scoping_cow_ajena",
                }
            )

    def test_a_designer_still_edits_everything(self):
        """The platform's own staff imply designer; the rule must not bite."""
        for view in (self.own_view, self.other_view):
            view.with_user(self.designer).write(
                {"arch": ARCH.replace("prueba", "del equipo")}
            )
        self.assertIn("del equipo", self.other_view.arch)

    def test_reading_stays_open(self):
        """Rendering any site needs its views; the rule only guards writing."""
        self.assertTrue(self.other_view.with_user(self.merchant).read(["name"]))
