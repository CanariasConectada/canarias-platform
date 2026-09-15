# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

MANAGER_GROUPS = (
    "base.group_user",
    "base.group_multi_company",
    "base.group_partner_manager",
    "event.group_event_manager",
    "mass_mailing.group_mass_mailing_user",
)
# Groups the profile must never carry: each one opens an app the request
# closed ("no debe tener acceso a Ventas", "no va a ver productos").
FORBIDDEN_GROUPS = (
    "sales_team.group_sale_salesman",
    "product.group_product_manager",
    "stock.group_stock_user",
    "purchase.group_purchase_user",
    "account.group_account_invoice",
    "merchant_group.group_merchant",
)

VISIBLE_ROOT_MENUS = (
    "mail.menu_root_discuss",
    "calendar.mail_menu_calendar",
    "contacts.menu_contacts",
    "event.event_main_menu",
    "mass_mailing.mass_mailing_menu_root",
    "website.menu_website_configuration",
)
VISIBLE_INNER_MENUS = (
    "contacts.res_partner_menu_contacts",
    "zca_manager_group.menu_zone_companies",
    "event.menu_event_event",
    "mass_mailing.mass_mailing_menu",
)
# Roots and entries of the apps the profile closes. Those of modules that
# are not installed here are skipped, not failed.
HIDDEN_MENUS = (
    "sale.sale_menu_root",
    "sale.product_menu_catalog",
    "stock.menu_stock_root",
    "purchase.menu_purchase_root",
    "account.menu_finance",
    "crm.crm_menu_root",
    "project.menu_main_pm",
    "base.menu_administration",
    "base.menu_management",
    "website_sale.menu_ecommerce",
    "website_sale.menu_product_pages",
    "company_certification.menu_certification_root",
    "partner_reviews.menu_partner_reviews_root",
    "spreadsheet_dashboard.spreadsheet_dashboard_menu_root",
)


@tagged("post_install", "-at_install")
class TestZcaManagerGroup(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group = cls.env.ref("zca_manager_group.group_zca_manager")
        Company = cls.env["res.company"]
        # The production database already carries the three zone
        # companies; a fresh one does not. Reuse or create, never
        # duplicate: two companies with the same key would give both
        # zones' shops to one manager.
        cls.zone_a = Company.search([("zone_company_key", "=", "guanarteme")], limit=1)
        if not cls.zone_a:
            cls.zone_a = Company.create(
                {"name": "ZCA Test Zone Guanarteme", "zone_company_key": "guanarteme"}
            )
        cls.zone_b = Company.search([("zone_company_key", "=", "tamaraceite")], limit=1)
        if not cls.zone_b:
            cls.zone_b = Company.create(
                {"name": "ZCA Test Zone Tamaraceite", "zone_company_key": "tamaraceite"}
            )
        cls.shop_a = Company.create(
            {"name": "ZCA Test Shop Guanarteme", "commercial_zone": "guanarteme"}
        )
        cls.shop_b = Company.create(
            {"name": "ZCA Test Shop Tamaraceite", "commercial_zone": "tamaraceite"}
        )
        # A contact of each shop. The ownership sync of
        # zone_company_ownership adds the zone company on create.
        cls.contact_a = cls.env["res.partner"].create(
            {"name": "ZCA Test Contact A", "company_ids": [(6, 0, [cls.shop_a.id])]}
        )
        cls.contact_b = cls.env["res.partner"].create(
            {"name": "ZCA Test Contact B", "company_ids": [(6, 0, [cls.shop_b.id])]}
        )
        # The zone's website: the real one where it exists, a test one
        # where it does not.
        cls.website_a = cls.env["website"].search(
            [("company_id", "=", cls.zone_a.id)], limit=1
        ) or cls.env["website"].create(
            {"name": "ZCA Test Site Guanarteme", "company_id": cls.zone_a.id}
        )
        cls.manager_a = cls._create_manager("zca_manager_guanarteme", cls.zone_a)
        cls.manager_b = cls._create_manager("zca_manager_tamaraceite", cls.zone_b)

    @classmethod
    def _create_manager(cls, login, zone):
        return (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": login,
                    "login": login,
                    "email": "%s@example.com" % login,
                    "company_id": zone.id,
                    "company_ids": [(6, 0, [zone.id])],
                    "group_ids": [(6, 0, [cls.group.id])],
                }
            )
        )

    def _visible_ids(self, user):
        """What load_menus() ends up showing: _visible_menu_ids() keeps a
        menu whose own gate passes even when an ancestor's does not, and
        load_menus() then drops every branch not attached to a root."""
        Menu = self.env["ir.ui.menu"].with_user(user)
        passing = set(Menu._visible_menu_ids())
        parent_of = {m.id: m.parent_id.id for m in Menu.sudo().browse(list(passing))}
        attached = set()
        for menu_id in passing:
            chain = []
            current = menu_id
            while current and current in passing:
                chain.append(current)
                current = parent_of[current]
            if not current:
                attached.update(chain)
        return attached

    def _menu(self, xmlid):
        menu = self.env.ref(xmlid, raise_if_not_found=False)
        if menu is None:
            self.skipTest("%s is not installed here" % xmlid.split(".")[0])
        return menu

    def _as(self, user, model):
        return self.env[model].with_user(user).with_company(user.company_id)

    # -- the group ---------------------------------------------------------

    def test_the_group_carries_the_manager_set_and_nothing_of_sales(self):
        implied = set(self.group.all_implied_ids.ids)
        for xmlid in MANAGER_GROUPS:
            with self.subTest(xmlid=xmlid):
                self.assertIn(self.env.ref(xmlid).id, implied)
                self.assertTrue(self.manager_a.has_group(xmlid))
        for xmlid in FORBIDDEN_GROUPS:
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group is None:
                continue
            with self.subTest(xmlid=xmlid):
                self.assertNotIn(group.id, implied)
                self.assertFalse(self.manager_a.has_group(xmlid))
        # A checkbox under "Extra rights", not a selection.
        self.assertFalse(self.group.privilege_id)

    def test_nobody_gets_it_by_default(self):
        self.assertNotIn(
            self.group, self.env.ref("base.default_user_group").all_implied_ids
        )
        merchant = self.env.ref(
            "merchant_group.group_merchant", raise_if_not_found=False
        )
        if merchant:
            self.assertNotIn(self.group, merchant.all_implied_ids)
        user = self.env["res.users"].create(
            {"name": "ZCA Fresh Internal", "login": "zca_manager_fresh"}
        )
        self.assertFalse(user.has_group("zca_manager_group.group_zca_manager"))

    # -- companies ---------------------------------------------------------

    def test_a_manager_reads_the_companies_of_their_zone_only(self):
        Company = self._as(self.manager_a, "res.company")
        seen = Company.search([])
        self.assertIn(self.zone_a, seen)
        self.assertIn(self.shop_a, seen)
        self.assertNotIn(self.zone_b, seen)
        self.assertNotIn(self.shop_b, seen)
        self.assertNotIn(self.env.ref("base.main_company"), seen)
        self.assertEqual(
            seen - self.zone_a,
            seen.filtered(lambda c: c.commercial_zone == "guanarteme"),
        )
        with self.assertRaises(AccessError):
            Company.browse(self.shop_b.id).read(["name"])
        with self.assertRaises(AccessError):
            Company.browse(self.zone_b.id).read(["name"])
        # Read only: not even their own zone company, let alone a shop.
        with self.assertRaises(AccessError):
            Company.browse(self.shop_a.id).write({"phone": "+34 000"})
        with self.assertRaises(AccessError):
            Company.browse(self.zone_a.id).write({"phone": "+34 000"})
        self.assertFalse(Company.has_access("create"))

    def test_the_companies_entry_hangs_under_contacts(self):
        menu = self.env.ref("zca_manager_group.menu_zone_companies")
        self.assertEqual(menu.parent_id, self.env.ref("contacts.menu_contacts"))
        self.assertEqual(menu.group_ids, self.group)
        self.assertEqual(menu.action.res_model, "res.company")

    # -- contacts ----------------------------------------------------------

    def test_a_manager_sees_the_contacts_of_their_zone_only(self):
        Partner = self._as(self.manager_a, "res.partner")
        seen = Partner.search([])
        self.assertIn(self.contact_a, seen)
        self.assertIn(self.shop_a.partner_id, seen)
        self.assertIn(self.zone_a.partner_id, seen)
        self.assertNotIn(self.contact_b, seen)
        self.assertNotIn(self.shop_b.partner_id, seen)
        with self.assertRaises(AccessError):
            Partner.browse(self.contact_b.id).read(["name"])
        # The zone's contacts are theirs to edit.
        Partner.browse(self.contact_a.id).write({"phone": "+34 000"})

    def test_a_contact_created_by_a_manager_belongs_to_the_zone(self):
        # ``partner_company_default`` (OCA) is what gives a new contact the
        # current company; it switches itself off under ``test_enable``
        # unless this context key is set, so set it to test what a user
        # of the form actually gets.
        partner = (
            self._as(self.manager_a, "res.partner")
            .with_context(test_partner_company_default=True)
            .create({"name": "ZCA Test New Contact", "email": "new@example.com"})
        )
        self.assertEqual(partner.sudo().company_ids, self.zone_a)
        self.assertIn(partner, self._as(self.manager_a, "res.partner").search([]))
        self.assertNotIn(partner, self._as(self.manager_b, "res.partner").search([]))

    # -- events ------------------------------------------------------------

    def test_a_manager_organises_and_publishes_the_events_of_their_zone(self):
        Event = self._as(self.manager_a, "event.event")
        defaults = Event.default_get(["website_id", "company_id"])
        self.assertEqual(
            self.env["website"].browse(defaults.get("website_id")).company_id,
            self.zone_a,
        )
        event = Event.create(
            {
                "name": "ZCA Test Event",
                "date_begin": "2026-10-01 10:00:00",
                "date_end": "2026-10-01 12:00:00",
                "website_id": defaults["website_id"],
            }
        )
        self.assertEqual(event.company_id, self.zone_a)
        self.assertEqual(event.website_id.company_id, self.zone_a)
        self.assertTrue(event.can_publish)
        event.write({"is_published": True})
        self.assertTrue(event.is_published)
        self.assertIn(event, Event.search([]))
        self.assertNotIn(event, self._as(self.manager_b, "event.event").search([]))
        with self.assertRaises(AccessError):
            self._as(self.manager_b, "event.event").browse(event.id).read(["name"])

    def test_an_event_of_a_shop_defaults_to_no_website(self):
        """The default is for the zone company only: a shop is not a zone."""
        defaults = (
            self.env["event.event"]
            .with_company(self.shop_a)
            .default_get(["website_id"])
        )
        self.assertFalse(defaults.get("website_id"))

    # -- mailings ----------------------------------------------------------

    def test_a_manager_works_on_the_mailings_of_their_zone_only(self):
        Mailing = self._as(self.manager_a, "mailing.mailing")
        mailing = Mailing.create(
            {
                "subject": "ZCA Test Mailing",
                "mailing_model_id": self.env.ref("base.model_res_partner").id,
                "body_html": "<p>Hello zone</p>",
            }
        )
        mailing_list = self._as(self.manager_a, "mailing.list").create(
            {"name": "ZCA Test List"}
        )
        self.assertIn(mailing, Mailing.search([]))
        self.assertIn(mailing_list, self._as(self.manager_a, "mailing.list").search([]))
        self.assertNotIn(
            mailing, self._as(self.manager_b, "mailing.mailing").search([])
        )
        self.assertNotIn(
            mailing_list, self._as(self.manager_b, "mailing.list").search([])
        )
        with self.assertRaises(AccessError):
            self._as(self.manager_b, "mailing.mailing").browse(mailing.id).read(
                ["subject"]
            )
        # A mailing an administrator creates FOR the zone, from the zone
        # company, is the zone's too.
        by_admin = (
            self.env["mailing.mailing"]
            .with_company(self.zone_a)
            .create(
                {
                    "subject": "ZCA Test Mailing by admin",
                    "mailing_model_id": self.env.ref("base.model_res_partner").id,
                    "body_html": "<p>Hello</p>",
                    "user_id": self.manager_a.id,
                }
            )
        )
        self.assertIn(by_admin, Mailing.search([]))

    # -- what stays closed -------------------------------------------------

    def test_a_manager_has_no_sales_and_no_products(self):
        closed = (
            "sale.order",
            "stock.picking",
            "purchase.order",
            "account.move",
            "crm.lead",
        )
        for model in closed:
            if model not in self.env:
                continue
            with self.subTest(model=model):
                self.assertFalse(
                    self.env[model].with_user(self.manager_a).has_access("read")
                )
        Product = self.env["product.template"].with_user(self.manager_a)
        # Core grants every internal user read on products (the catalogue
        # behind a sale line); the profile closes every door to it instead.
        for mode in ("write", "create", "unlink"):
            with self.subTest(mode=mode):
                self.assertFalse(Product.has_access(mode))

    def test_a_manager_sees_the_profile_menus(self):
        visible = self._visible_ids(self.manager_a)
        for xmlid in VISIBLE_ROOT_MENUS:
            with self.subTest(xmlid=xmlid):
                menu = self._menu(xmlid)
                self.assertFalse(menu.parent_id, "%s is not a root menu" % xmlid)
                self.assertIn(menu.id, visible)
        for xmlid in VISIBLE_INNER_MENUS:
            with self.subTest(xmlid=xmlid):
                self.assertIn(self._menu(xmlid).id, visible)

    def test_a_manager_does_not_see_the_rest(self):
        visible = self._visible_ids(self.manager_a)
        for xmlid in HIDDEN_MENUS:
            with self.subTest(xmlid=xmlid):
                self.assertNotIn(self._menu(xmlid).id, visible)

    def test_the_product_pages_gate_is_owned_in_replace_form(self):
        self.assertEqual(
            self.env.ref("website_sale.menu_product_pages").group_ids,
            self.env.ref("sales_team.group_sale_salesman")
            | self.env.ref("website.group_website_designer"),
        )

    # -- discuss -----------------------------------------------------------

    def test_a_manager_is_seated_in_the_channel_of_their_zone(self):
        channel = self.env.ref("discuss_channel_zone.channel_guanarteme")
        general = self.env.ref("discuss_channel_zone.channel_canarias")
        self.assertEqual(self.manager_a._get_chat_zone(), "guanarteme")
        self.assertIn(self.manager_a.partner_id, channel.channel_member_ids.partner_id)
        self.assertIn(self.manager_a.partner_id, general.channel_member_ids.partner_id)
        self.assertNotIn(
            self.manager_b.partner_id, channel.channel_member_ids.partner_id
        )

    def test_ticking_the_group_later_seats_the_user_right_away(self):
        channel = self.env.ref("discuss_channel_zone.channel_guanarteme")
        user = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "ZCA Late Manager",
                    "login": "zca_manager_late",
                    "company_id": self.zone_a.id,
                    "company_ids": [(6, 0, [self.zone_a.id])],
                    "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
                }
            )
        )
        self.assertNotIn(user.partner_id, channel.channel_member_ids.partner_id)
        user.write({"group_ids": [(4, self.group.id)]})
        self.assertEqual(user._get_chat_zone(), "guanarteme")
        self.assertIn(user.partner_id, channel.channel_member_ids.partner_id)
