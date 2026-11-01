# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import importlib.util
import os
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.modules.module import get_module_path
from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tools import mute_logger

from .common import CommunityMixin


class MemberParityMixin(CommunityMixin):
    """A registered resident next to the populations it must not be mixed with."""

    @classmethod
    def _setup_parity_fixtures(cls):
        cls._setup_community_fixtures()
        cls.admin_channel = cls.env.ref("mail.channel_admin")
        cls.Member = cls.env["discuss.channel.member"]
        cls.Users = cls.env["res.users"].with_context(no_reset_password=True)

    @classmethod
    def _make_user(cls, login, groups, company=None):
        company = company or cls.main_company
        return cls.Users.create(
            {
                "name": login.replace("_", " ").title(),
                "login": login,
                "password": login,
                "email": "%s@example.com" % login,
                "company_id": company.id,
                "company_ids": [(6, 0, company.ids)],
                "group_ids": [(6, 0, groups.ids)],
            }
        )

    @classmethod
    def _make_registered_member(cls, login, zone="guanarteme"):
        """A resident through the signup door: portal first, then promoted."""
        user = cls._make_user(login, cls.portal_group)
        return user._promote_to_community_member(zone=zone)

    def _seat(self, user, channel):
        return self.Member.sudo().search(
            [
                ("channel_id", "=", channel.id),
                ("partner_id", "=", user.partner_id.id),
            ]
        )

    def _readable(self, user, channels):
        return (
            self.env["discuss.channel"]
            .with_user(user)
            .search([("id", "in", channels.ids)])
        )

    def _rpc_members(self, user, channel):
        rows = self.Member.with_user(user).search_read(
            [("channel_id", "=", channel.id)], ["partner_id"]
        )
        return {row["partner_id"][0] for row in rows if row["partner_id"]}


@tagged("post_install", "-at_install")
class TestCommunityMemberParity(MemberParityMixin, TransactionCase):
    """Registered residents get exactly the profile guests get."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_parity_fixtures()
        cls.resident = cls._make_registered_member("dcm_parity_resident")

    # ------------------------------------------------------------------
    # The population
    # ------------------------------------------------------------------

    def test_promoted_resident_is_a_community_member(self):
        self.assertTrue(self.resident.is_community_member)
        self.assertFalse(self.resident.is_community_guest)
        self.assertEqual(self.resident.odoobot_state, "disabled")
        self.assertFalse(self.employee.is_community_member)

    def test_admin_holding_the_group_is_not_a_member(self):
        admin = self._make_user(
            "dcm_parity_admin",
            self.env.ref("base.group_system") | self.community_group,
        )
        self.assertFalse(admin.is_community_member)
        self.assertFalse(admin._zone_self_managed_users())
        self.assertEqual(
            self._readable(admin, self.employees_channel), self.employees_channel
        )

    # ------------------------------------------------------------------
    # Channels of their own choice
    # ------------------------------------------------------------------

    def test_resident_choice_survives_the_nightly_reconciliation(self):
        """Joined a foreign zone, left its own: the cron keeps both choices."""
        self.assertTrue(self._seat(self.resident, self.channel_guanarteme))
        self.channel_lomo.with_user(self.resident).channel_join()
        self.channel_guanarteme.with_user(self.resident).action_unfollow()

        self.channel_general.with_user(self.resident).action_unfollow()

        self.env["res.users"]._cron_sync_zone_channels()

        self.assertTrue(self._seat(self.resident, self.channel_lomo))
        self.assertFalse(self._seat(self.resident, self.channel_guanarteme))
        self.assertFalse(
            self._seat(self.resident, self.channel_general),
            "a left 'Canarias Conectada' must not come back overnight",
        )
        # A direct sync (zone change path) may add seats but never removes
        # a self-managed user's own choices.
        counters = self.resident._sync_zone_channels()
        self.assertEqual(counters["removed"], 0)
        self.assertTrue(self._seat(self.resident, self.channel_lomo))

    # ------------------------------------------------------------------
    # Staff channels
    # ------------------------------------------------------------------

    def test_resident_is_not_seated_in_general_on_creation_nor_regroup(self):
        self.assertFalse(self._seat(self.resident, self.employees_channel))
        self.assertFalse(self._seat(self.resident, self.admin_channel))
        # Regroup: every path of core's auto-subscription funnels through
        # ``_subscribe_users_automatically_get_members``.
        self.resident.write({"group_ids": [(3, self.community_group.id)]})
        self.assertFalse(self._seat(self.resident, self.employees_channel))
        self.resident.write({"group_ids": [(4, self.community_group.id)]})
        self.assertFalse(self._seat(self.resident, self.employees_channel))
        self.resident.write({"group_ids": [(4, self.internal_group.id)]})
        self.assertFalse(self._seat(self.resident, self.employees_channel))
        self.resident.write(
            {"group_ids": [(6, 0, self.env["res.users"]._community_group_ids())]}
        )
        self.assertFalse(self._seat(self.resident, self.employees_channel))
        self.employees_channel._subscribe_users_automatically()
        self.assertFalse(self._seat(self.resident, self.employees_channel))
        self.assertFalse(self._seat(self.member, self.employees_channel))
        # Control: an employee IS seated.
        self.assertTrue(self._seat(self.employee, self.employees_channel))

    def test_carve_out_spares_staff_holding_the_community_group(self):
        """Admins and merchants holding the group are auto-seated in general."""
        admin = self._make_user(
            "dcm_carve_admin",
            self.env.ref("base.group_system") | self.community_group,
        )
        self.assertTrue(self._seat(admin, self.employees_channel))
        merchant_group = self.env.ref(
            "merchant_group.group_merchant", raise_if_not_found=False
        )
        if merchant_group:
            merchant = self._make_user(
                "dcm_carve_merchant", merchant_group | self.community_group
            )
            self.assertTrue(self._seat(merchant, self.employees_channel))
        pure = self._make_user(
            "dcm_carve_member", self.internal_group | self.community_group
        )
        self.assertFalse(self._seat(pure, self.employees_channel))

    def test_group_side_change_refreshes_the_cached_rules(self):
        """Adding/removing the user FROM THE GROUP flips visibility at once."""
        user = self._make_user("dcm_group_side", self.internal_group)

        def sees_general():
            return bool(self._readable(user, self.employees_channel))

        self.assertTrue(sees_general())
        self.community_group.write({"user_ids": [(4, user.id)]})
        self.assertTrue(user.is_community_member)
        self.assertFalse(sees_general())
        self.community_group.write({"user_ids": [(3, user.id)]})
        self.assertFalse(user.is_community_member)
        self.assertTrue(sees_general())

    # ------------------------------------------------------------------
    # Conversations and people
    # ------------------------------------------------------------------

    def _self_join(self, user, channel):
        return self.Member.with_user(user).create(
            {"channel_id": channel.id, "partner_id": user.partner_id.id}
        )

    @mute_logger("odoo.addons.base.models.ir_rule", "odoo.orm.models")
    def test_resident_cannot_join_a_foreign_group(self):
        group = (
            self.env["discuss.channel"]
            .with_user(self.employee)
            ._create_group(partners_to=self.member.partner_id.ids)
        )
        with self.assertRaises(AccessError):
            self._self_join(self.resident, group)
        self.assertNotIn(self.resident.partner_id, group.sudo().channel_partner_ids)

    @mute_logger("odoo.addons.base.models.ir_rule", "odoo.orm.models")
    def test_resident_cannot_join_a_foreign_chat(self):
        chat = (
            self.env["discuss.channel"]
            .with_user(self.employee)
            ._get_or_create_chat(partners_to=self.member.partner_id.ids)
        )
        chat.with_user(self.member).action_unfollow()
        # Whichever check fires first, the resident must not end up seated.
        with self.assertRaises(Exception) as caught:
            self._self_join(self.resident, chat)
        self.assertIsInstance(
            caught.exception, (AccessError, UserError, ValidationError)
        )
        self.assertNotIn(self.resident.partner_id, chat.sudo().channel_partner_ids)

    def test_resident_creates_its_own_open_channel(self):
        """Core would gate a new channel on employees, which the rule hides."""
        channel = (
            self.env["discuss.channel"]
            .with_user(self.resident)
            ._create_channel(name="DCM Resident Room", group_id=None)
        )
        self.assertFalse(channel.sudo().group_public_id)
        self.assertEqual(self._readable(self.resident, channel), channel)
        plain = (
            self.env["discuss.channel"]
            .with_user(self.resident)
            .create({"name": "DCM Resident Plain Room"})
        )
        self.assertFalse(plain.sudo().group_public_id)
        # An employee's plain new channel keeps core's default.
        staff = (
            self.env["discuss.channel"]
            .with_user(self.employee)
            .create({"name": "DCM Employee Room"})
        )
        self.assertEqual(staff.sudo().group_public_id, self.internal_group)

    def test_resident_people_search_offers_no_directory(self):
        """Empty mention/invite searches only return its conversation partners."""
        outsider = self._make_user("dcm_outsider", self.internal_group)
        Partner = self.env["res.partner"].with_user(self.resident)
        result = Partner.get_mention_suggestions("", limit=50)
        mentioned = {row["id"] for row in result.get("res.partner", [])}
        self.assertLessEqual(mentioned, {self.resident.partner_id.id})
        invite = Partner.search_for_channel_invite("", self.channel_lomo.id)
        self.assertFalse(invite["partner_ids"])
        self.assertEqual(invite["count"], 0)
        # A chat partner becomes findable; a stranger never is.
        self.env["discuss.channel"].with_user(self.employee)._get_or_create_chat(
            partners_to=self.resident.partner_id.ids
        )
        result = Partner.get_mention_suggestions("", limit=50)
        mentioned = {row["id"] for row in result.get("res.partner", [])}
        self.assertIn(self.employee.partner_id.id, mentioned)
        self.assertNotIn(outsider.partner_id.id, mentioned)
        self.assertNotIn(self.env.ref("base.partner_admin").id, mentioned)
        # Control: an employee gets the directory.
        staff_result = (
            self.env["res.partner"]
            .with_user(self.employee)
            .get_mention_suggestions("dcm outsider", limit=50)
        )
        self.assertIn(
            outsider.partner_id.id,
            {row["id"] for row in staff_result.get("res.partner", [])},
        )

    @mute_logger("odoo.addons.base.models.ir_rule", "odoo.orm.models")
    def test_resident_cannot_read_general_nor_its_messages(self):
        message = self.employees_channel.sudo().message_post(
            body="DCM staff only", message_type="comment"
        )
        self.employees_channel.sudo()._add_members(
            partners=self.resident.partner_id, post_joined_message=False
        )
        self.assertFalse(self._readable(self.resident, self.employees_channel))
        with self.assertRaises(AccessError):
            self.employees_channel.with_user(self.resident).read(["name"])
        self.assertFalse(
            self.env["mail.message"]
            .with_user(self.resident)
            .search(
                [
                    ("model", "=", "discuss.channel"),
                    ("res_id", "=", self.employees_channel.id),
                ]
            )
        )
        with self.assertRaises(AccessError):
            message.with_user(self.resident).read(["body"])
        self.assertFalse(self._rpc_members(self.resident, self.employees_channel))

    @mute_logger("odoo.addons.base.models.ir_rule", "odoo.orm.models")
    def test_resident_cannot_join_general(self):
        with self.assertRaises(AccessError):
            self.employees_channel.with_user(self.resident).channel_join()

    @mute_logger("odoo.addons.base.models.ir_rule", "odoo.orm.models")
    def test_resident_cannot_read_any_employee_only_channel(self):
        staff = self.env["discuss.channel"].create(
            {
                "name": "DCM Staff Room",
                "channel_type": "channel",
                "group_public_id": self.internal_group.id,
            }
        )
        staff._add_members(partners=self.resident.partner_id)
        self.assertFalse(self._readable(self.resident, staff))
        self.assertEqual(self._readable(self.employee, staff), staff)

    def test_resident_reads_only_its_own_rows_in_community_channels(self):
        everyone = set(self.channel_general.sudo().channel_member_ids.partner_id.ids)
        self.assertIn(self.employee.partner_id.id, everyone)
        self.assertEqual(
            self._rpc_members(self.resident, self.channel_general),
            {self.resident.partner_id.id},
        )
        self.assertEqual(
            self._readable(self.resident, self.zone_channels), self.zone_channels
        )

    # ------------------------------------------------------------------
    # Cleanup and garbage collection
    # ------------------------------------------------------------------

    def test_cleanup_removes_member_seats_in_staff_channels(self):
        """What the 19.0.1.8.0 migration does to the residents in prod."""
        staff = self.env["discuss.channel"].create(
            {
                "name": "DCM Staff Room II",
                "channel_type": "channel",
                "group_public_id": self.internal_group.id,
            }
        )
        guest = self.env["res.users"]._create_community_guest(zone="guanarteme")
        seated = self.resident | self.member | guest | self.employee
        for channel in (self.employees_channel, self.admin_channel, staff):
            channel.sudo()._add_members(
                partners=seated.partner_id, post_joined_message=False
            )

        counters = self.env["res.users"]._cleanup_community_members()

        self.assertGreaterEqual(counters["staff_seats"], 9)
        for user in self.resident | self.member | guest:
            for channel in (self.employees_channel, self.admin_channel, staff):
                self.assertFalse(self._seat(user, channel))
            self.assertTrue(self._seat(user, self.channel_general))
        for channel in (self.employees_channel, self.admin_channel, staff):
            self.assertTrue(self._seat(self.employee, channel))
        again = self.env["res.users"]._cleanup_community_members()
        self.assertEqual(again["staff_seats"], 0)

    def _migration(self):
        path = os.path.join(
            get_module_path("discuss_community"),
            "migrations",
            "19.0.1.8.0",
            "post-migration.py",
        )
        spec = importlib.util.spec_from_file_location("dcm_migration_1_8", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_migration_removes_member_staff_seats(self):
        guest = self.env["res.users"]._create_community_guest(zone="guanarteme")
        seated = self.resident | guest | self.employee
        self.employees_channel.sudo()._add_members(
            partners=seated.partner_id, post_joined_message=False
        )
        migration = self._migration()
        self.env.flush_all()
        migration.migrate(self.env.cr, None)  # fresh install: no-op
        self.env.invalidate_all()
        self.assertTrue(self._seat(self.resident, self.employees_channel))
        migration.migrate(self.env.cr, "19.0.1.7.0")
        self.env.invalidate_all()
        self.assertFalse(self._seat(self.resident, self.employees_channel))
        self.assertFalse(self._seat(guest, self.employees_channel))
        self.assertTrue(self._seat(self.employee, self.employees_channel))

    def test_gc_ignores_registered_residents(self):
        """The garbage collector is for disposable guests only."""
        old = fields.Datetime.now() - timedelta(days=60)
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE res_users SET create_date = %s WHERE id = %s",
            (old, self.resident.id),
        )
        self.env.invalidate_all()
        self.env["res.users"]._gc_community_guests()
        self.assertTrue(self.resident.exists() and self.resident.active)
        counters = dict.fromkeys(
            (
                "users_removed",
                "users_archived",
                "partners_removed",
                "partners_archived",
                "memberships",
                "devices",
            ),
            0,
        )
        self.resident._community_guest_remove(counters)
        self.assertTrue(self.resident.exists() and self.resident.active)
        self.assertFalse(any(counters.values()))


@tagged("post_install", "-at_install")
class TestCommunityStaffPopulations(MemberParityMixin, TransactionCase):
    """Merchants and zone managers are never trimmed, community group or not."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_parity_fixtures()

    def _group_or_skip(self, xmlid):
        group = self.env.ref(xmlid, raise_if_not_found=False)
        if not group:
            self.skipTest("%s is not installed" % xmlid.split(".")[0])
        return group

    def _assert_full_profile(self, user):
        self.assertFalse(user.is_community_member)
        self.assertFalse(user._zone_self_managed_users())
        self.assertEqual(
            self._readable(user, self.employees_channel), self.employees_channel
        )
        self.assertEqual(
            self._rpc_members(user, self.channel_general),
            set(self.channel_general.sudo().channel_member_ids.partner_id.ids),
        )
        discuss_tree = set(
            self.env["ir.ui.menu"]
            .sudo()
            .search([("id", "child_of", self.discuss_root.id)])
            .ids
        )
        visible = self.env["ir.ui.menu"].with_user(user)._visible_menu_ids()
        self.assertTrue(set(visible) - discuss_tree, "the backend must not be trimmed")

    def _check_population(self, xmlid, login, company=None):
        group = self._group_or_skip(xmlid)
        plain = self._make_user(login, group, company)
        self._assert_full_profile(plain)
        # Even when the community group lands on the account by mistake.
        mixed = self._make_user(login + "_mixed", group | self.community_group, company)
        self._assert_full_profile(mixed)
        # The cleanup of the 19.0.1.8.0 migration leaves their seats alone.
        self.employees_channel.sudo()._add_members(
            partners=(plain | mixed).partner_id, post_joined_message=False
        )
        self.env["res.users"]._cleanup_community_members()
        self.assertTrue(self._seat(plain, self.employees_channel))
        self.assertTrue(self._seat(mixed, self.employees_channel))

    def test_migrated_merchant_is_exempt(self):
        xmlid = "discuss_community.group_migrated_merchant"
        group = self.env.ref(xmlid, raise_if_not_found=False)
        if not group:
            group = self.env["res.groups"].create({"name": "DCM Migrated Merchant"})
            self.env["ir.model.data"].create(
                {
                    "name": "group_migrated_merchant",
                    "module": "discuss_community",
                    "model": "res.groups",
                    "res_id": group.id,
                }
            )
        user = self._make_user(
            "dcm_migrated_mixed", self.internal_group | group | self.community_group
        )
        self.assertFalse(user.is_community_member)
        self.assertFalse(user._zone_self_managed_users())
        self.assertNotIn(user, self.env["res.users"]._search_all_community_members())

    def test_merchant_keeps_the_full_profile(self):
        self._check_population("merchant_group.group_merchant", "dcm_comercio")

    def test_zone_manager_keeps_the_full_profile(self):
        self._group_or_skip("zca_manager_group.group_zca_manager")
        # A zone manager must belong to a zone company (zca_manager_group).
        Company = self.env["res.company"]
        zone = Company.search([("zone_company_key", "=", "guanarteme")], limit=1)
        zone = zone or Company.create(
            {"name": "DCM Zone Guanarteme", "zone_company_key": "guanarteme"}
        )
        self._check_population(
            "zca_manager_group.group_zca_manager", "dcm_gestor_zca", zone
        )


@tagged("post_install", "-at_install")
class TestCommunityMemberSession(MemberParityMixin, HttpCase):
    """The web client learns the member profile from ``session_info``."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_parity_fixtures()
        cls.resident = cls._make_registered_member("dcm_session_resident")
        cls._prepare_settings(cls.resident | cls.employee)

    @classmethod
    def _prepare_settings(cls, users):
        """Create the Discuss settings up front: the session route is
        read-only and would otherwise retry to create them (logged ERROR)."""
        Settings = cls.env["res.users.settings"]
        for user in users:
            Settings._find_or_create_for_user(user)

    def _session_info(self, login):
        self.authenticate(login, login)
        return self.make_jsonrpc_request("/web/session/get_session_info")

    def test_resident_session_is_a_member_landing_in_the_community_channel(self):
        info = self._session_info("dcm_session_resident")
        self.assertTrue(info["is_community_member"])
        self.assertFalse(info["is_community_guest"])
        self.assertEqual(info["community_default_channel_id"], self.channel_general.id)

    def test_employee_session_is_not_a_member(self):
        info = self._session_info("dcm_employee")
        self.assertFalse(info["is_community_member"])
        self.assertNotIn("community_default_channel_id", info)
