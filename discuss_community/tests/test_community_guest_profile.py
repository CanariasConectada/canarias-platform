# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import AccessError
from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tools import mute_logger

from .common import CommunityMixin


class GuestProfileMixin(CommunityMixin):
    @classmethod
    def _setup_guest_profile_fixtures(cls):
        cls._setup_community_fixtures()
        cls.admin_channel = cls.env.ref("mail.channel_admin")
        cls.odoobot = cls.env.ref("base.partner_root")
        cls.guest = cls.env["res.users"]._create_community_guest(zone="guanarteme")


@tagged("post_install", "-at_install")
class TestCommunityGuestChannels(GuestProfileMixin, TransactionCase):
    """What a community guest may read and join in Discuss."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_guest_profile_fixtures()

    def _readable(self, user, channels):
        return (
            self.env["discuss.channel"]
            .with_user(user)
            .search([("id", "in", channels.ids)])
        )

    def test_guest_reads_own_and_open_channels_only(self):
        """Member channels + open channels; not staff, not other zones."""
        everything = self.zone_channels | self.employees_channel | self.admin_channel
        readable = self._readable(self.guest, everything)
        self.assertEqual(readable, self.channel_general | self.channel_guanarteme)

    @mute_logger("odoo.addons.base.models.ir_rule", "odoo.orm.models")
    def test_guest_cannot_read_general_even_when_seated(self):
        """The legacy prod case: a guest seated in "general" before the fix."""
        self.employees_channel.sudo()._add_members(
            partners=self.guest.partner_id, post_joined_message=False
        )
        self.assertFalse(self._readable(self.guest, self.employees_channel))
        with self.assertRaises(AccessError):
            self.employees_channel.with_user(self.guest).read(["name"])

    @mute_logger("odoo.addons.base.models.ir_rule", "odoo.orm.models")
    def test_guest_cannot_join_general(self):
        with self.assertRaises(AccessError):
            self.employees_channel.with_user(self.guest).channel_join()
        with self.assertRaises(AccessError):
            self.env["discuss.channel.member"].with_user(self.guest).create(
                {
                    "channel_id": self.employees_channel.id,
                    "partner_id": self.guest.partner_id.id,
                }
            )

    def test_guest_can_join_open_channel(self):
        """The join restriction is about staff channels, not joining at all."""
        self.env["discuss.channel.member"].sudo().search(
            [
                ("channel_id", "=", self.channel_general.id),
                ("partner_id", "=", self.guest.partner_id.id),
            ]
        ).unlink()
        self.channel_general.with_user(self.guest).channel_join()
        self.assertIn(self.guest.partner_id, self.channel_general.channel_partner_ids)

    def test_employee_still_reads_and_joins_general(self):
        """Non-guests are untouched by the guest rules."""
        self.assertEqual(
            self._readable(self.employee, self.employees_channel),
            self.employees_channel,
        )
        self.env["discuss.channel.member"].sudo().search(
            [
                ("channel_id", "=", self.employees_channel.id),
                ("partner_id", "=", self.employee.partner_id.id),
            ]
        ).unlink()
        self.employees_channel.with_user(self.employee).channel_join()
        self.assertIn(
            self.employee.partner_id, self.employees_channel.channel_partner_ids
        )

    def test_registered_member_is_not_a_guest(self):
        """A registered resident keeps core's channel access."""
        self.assertFalse(self.member.is_community_guest)
        self.assertIn(
            self.channel_tamaraceite,
            self._readable(self.member, self.zone_channels),
        )

    def test_guest_keeps_direct_chats(self):
        """Conversations the guest is part of stay readable."""
        chat = (
            self.env["discuss.channel"]
            .with_user(self.employee)
            ._get_or_create_chat(partners_to=self.guest.partner_id.ids)
        )
        self.assertEqual(self._readable(self.guest, chat), chat)


@tagged("post_install", "-at_install")
class TestCommunityGuestMembers(GuestProfileMixin, TransactionCase):
    """Who a community guest can see in a channel, through plain RPC."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_guest_profile_fixtures()
        # Somebody else in the guest's channels: the employee is seated in the
        # general community channel by the zone sync, the member in both.
        cls.chat = (
            cls.env["discuss.channel"]
            .with_user(cls.employee)
            ._get_or_create_chat(partners_to=cls.guest.partner_id.ids)
        )

    def _rpc_members(self, user, channel):
        rows = (
            self.env["discuss.channel.member"]
            .with_user(user)
            .search_read([("channel_id", "=", channel.id)], ["partner_id"])
        )
        return {row["partner_id"][0] for row in rows if row["partner_id"]}

    def test_guest_reads_only_its_own_row_in_a_channel(self):
        everyone = set(self.channel_general.sudo().channel_member_ids.partner_id.ids)
        self.assertIn(self.employee.partner_id.id, everyone)
        self.assertIn(self.member.partner_id.id, everyone)
        self.assertEqual(
            self._rpc_members(self.guest, self.channel_general),
            {self.guest.partner_id.id},
        )
        self.assertEqual(
            self._rpc_members(self.guest, self.channel_guanarteme),
            {self.guest.partner_id.id},
        )
        # And no roster of channels it is not in either.
        self.assertFalse(self._rpc_members(self.guest, self.channel_tamaraceite))

    def test_guest_reads_the_members_of_its_chats(self):
        self.assertEqual(
            self._rpc_members(self.guest, self.chat),
            {self.guest.partner_id.id, self.employee.partner_id.id},
        )

    def test_guest_reads_nothing_of_staff_channels(self):
        self.employees_channel.sudo()._add_members(
            partners=self.guest.partner_id, post_joined_message=False
        )
        self.assertFalse(self._rpc_members(self.guest, self.employees_channel))

    def test_employee_still_reads_the_roster(self):
        self.assertEqual(
            self._rpc_members(self.employee, self.channel_general),
            set(self.channel_general.sudo().channel_member_ids.partner_id.ids),
        )

    def test_flag_change_refreshes_the_cached_rules(self):
        """Rule domains are cached per user: flipping the flag must reset them."""
        self.assertIn(
            self.employee.partner_id.id,
            self._rpc_members(self.employee, self.channel_general),
        )
        self.assertTrue(
            self.env["discuss.channel"]
            .with_user(self.employee)
            .search([("id", "=", self.employees_channel.id)])
        )
        self.employee.is_community_guest = True
        self.assertEqual(
            self._rpc_members(self.employee, self.channel_general),
            {self.employee.partner_id.id},
        )
        self.assertFalse(
            self.env["discuss.channel"]
            .with_user(self.employee)
            .search([("id", "=", self.employees_channel.id)])
        )
        self.employee.is_community_guest = False
        self.assertTrue(
            self.env["discuss.channel"]
            .with_user(self.employee)
            .search([("id", "=", self.employees_channel.id)])
        )


@tagged("post_install", "-at_install")
class TestCommunityGuestMentions(GuestProfileMixin, TransactionCase):
    """@-mention suggestions must not leak a channel's roster to a guest."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_guest_profile_fixtures()
        # The employee has spoken in the community channel; the resident
        # member is seated there too but never posted.
        cls.channel_general.with_user(cls.employee).message_post(
            body="DCM hello neighbours",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        cls.chat = (
            cls.env["discuss.channel"]
            .with_user(cls.member)
            ._get_or_create_chat(partners_to=cls.guest.partner_id.ids)
        )

    def _suggested(self, user, channel, search="", limit=1000):
        result = (
            self.env["res.partner"]
            .with_user(user)
            .get_mention_suggestions_from_channel(channel.id, search, limit=limit)
        )
        if not result:  # core answers [] for a channel it cannot find
            return set()
        return {row["id"] for row in result.get("res.partner", [])}

    def test_guest_gets_only_authors_and_itself_in_a_channel(self):
        suggested = self._suggested(self.guest, self.channel_general)
        self.assertIn(self.employee.partner_id.id, suggested)
        self.assertNotIn(self.member.partner_id.id, suggested)
        self.assertLessEqual(suggested, self._authors() | {self.guest.partner_id.id})

    def _authors(self):
        messages = (
            self.env["mail.message"]
            .sudo()
            .search(
                [
                    ("model", "=", "discuss.channel"),
                    ("res_id", "=", self.channel_general.id),
                    ("message_type", "=", "comment"),
                ]
            )
        )
        return set(messages.author_id.ids)

    def test_guest_limit_is_capped(self):
        self.assertLessEqual(len(self._suggested(self.guest, self.channel_general)), 8)

    def test_guest_gets_the_members_of_its_chat(self):
        self.assertIn(self.member.partner_id.id, self._suggested(self.guest, self.chat))

    def test_guest_gets_nothing_from_a_channel_it_cannot_read(self):
        self.assertFalse(self._suggested(self.guest, self.employees_channel))

    def test_employee_still_gets_silent_members(self):
        suggested = self._suggested(
            self.employee, self.channel_general, search="DCM Member"
        )
        self.assertIn(self.member.partner_id.id, suggested)


@tagged("post_install", "-at_install")
class TestCommunityGuestProfile(GuestProfileMixin, TransactionCase):
    """Menus, OdooBot and the one-time cleanup of existing guests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_guest_profile_fixtures()
        cls.config_menu = cls.env.ref("mail.menu_configuration")

    def _visible_menus(self, user):
        return self.env["ir.ui.menu"].with_user(user)._visible_menu_ids()

    def test_guest_has_no_discuss_configuration_menu(self):
        visible = self._visible_menus(self.guest)
        self.assertIn(self.discuss_root.id, visible)
        self.assertNotIn(self.config_menu.id, visible)
        for child in self.config_menu.child_id:
            self.assertNotIn(child.id, visible)

    def test_configuration_menu_kept_for_non_guests(self):
        """Guests only: no group was put on the core menu."""
        self.assertFalse(self.config_menu.group_ids - self.internal_group)
        self.assertIn(self.config_menu.id, self._visible_menus(self.employee))
        self.assertIn(self.config_menu.id, self._visible_menus(self.member))

    def _odoobot_chats(self, user):
        return (
            self.env["discuss.channel.member"]
            .sudo()
            .search(
                [
                    ("channel_id.channel_type", "=", "chat"),
                    ("partner_id", "=", user.partner_id.id),
                    ("channel_id.channel_member_ids.partner_id", "=", self.odoobot.id),
                ]
            )
        )

    def test_new_guest_is_never_onboarded_by_odoobot(self):
        self.assertEqual(self.guest.odoobot_state, "disabled")
        self.guest.with_user(self.guest)._on_webclient_bootstrap()
        self.assertFalse(self._odoobot_chats(self.guest))

    def test_legacy_guest_bootstrap_disables_odoobot(self):
        self.guest.odoobot_state = "not_initialized"
        self.guest.with_user(self.guest)._on_webclient_bootstrap()
        self.assertEqual(self.guest.odoobot_state, "disabled")
        self.assertFalse(self._odoobot_chats(self.guest))

    def test_employee_still_onboarded_by_odoobot(self):
        self.employee.odoobot_state = "not_initialized"
        self.employee.with_user(self.employee)._on_webclient_bootstrap()
        self.assertTrue(self._odoobot_chats(self.employee))

    def test_cleanup_brings_legacy_guests_to_the_profile(self):
        """What the 19.0.1.4.0 migration does to the guests already in prod."""
        guest = self.guest
        guest.odoobot_state = "not_initialized"
        guest._init_odoobot()
        self.employees_channel.sudo()._add_members(
            partners=guest.partner_id, post_joined_message=False
        )
        self.employee.odoobot_state = "not_initialized"
        self.employee._init_odoobot()
        self.assertTrue(self._odoobot_chats(guest))

        counters = self.env["res.users"]._cleanup_community_guests()

        self.assertGreaterEqual(counters["staff_seats"], 1)
        self.assertGreaterEqual(counters["odoobot_chats"], 1)
        self.assertNotIn(guest.partner_id, self.employees_channel.channel_partner_ids)
        self.assertFalse(self._odoobot_chats(guest))
        self.assertEqual(guest.odoobot_state, "disabled")
        # Guests keep their community seats; employees keep everything.
        self.assertEqual(
            self._zone_channels_of(guest),
            self.channel_general | self.channel_guanarteme,
        )
        self.assertIn(
            self.employee.partner_id, self.employees_channel.channel_partner_ids
        )
        self.assertTrue(self._odoobot_chats(self.employee))
        # Idempotent.
        again = self.env["res.users"]._cleanup_community_guests()
        self.assertEqual(
            again, {"staff_seats": 0, "odoobot_chats": 0, "odoobot_disabled": 0}
        )


@tagged("post_install", "-at_install")
class TestCommunityGuestTour(GuestProfileMixin, HttpCase):
    """The guest profile as rendered by the real web client."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_guest_profile_fixtures()
        cls.guest.password = "dcm_guest_pwd"

    def test_guest_discuss_profile_tour(self):
        self.start_tour(
            "/odoo/action-mail.action_discuss",
            "discuss_community_guest_profile",
            login=self.guest.login,
        )

    def test_employee_discuss_profile_tour(self):
        # A small channel of its own: the stock header must be there, and a
        # member list of hundreds of real accounts would only slow the tour.
        channel = self.env["discuss.channel"].create(
            {"name": "DCM Open Channel", "channel_type": "channel"}
        )
        channel._add_members(users=self.employee, post_joined_message=False)
        self.start_tour(
            "/odoo/action-mail.action_discuss?active_id=discuss.channel_%s"
            % channel.id,
            "discuss_community_employee_profile",
            login="dcm_employee",
        )
