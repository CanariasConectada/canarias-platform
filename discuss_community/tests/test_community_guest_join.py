# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from .common import CommunityMixin


@tagged("post_install", "-at_install")
class TestCommunityGuestJoin(CommunityMixin, TransactionCase):
    """What a guest may seat itself (or others) in, over the ORM as the guest."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_community_fixtures()
        cls.guest = cls.env["res.users"]._create_community_guest(zone="guanarteme")
        cls.Channel = cls.env["discuss.channel"]
        cls.Member = cls.env["discuss.channel.member"]
        # A private group between two other people.
        cls.foreign_group = cls.Channel.with_user(cls.employee)._create_group(
            partners_to=cls.member.partner_id.ids
        )

    def _self_join(self, channel):
        return self.Member.with_user(self.guest).create(
            {"channel_id": channel.id, "partner_id": self.guest.partner_id.id}
        )

    @mute_logger("odoo.addons.base.models.ir_rule", "odoo.orm.models")
    def test_guest_cannot_join_a_foreign_group(self):
        with self.assertRaises(AccessError):
            self._self_join(self.foreign_group)
        with self.assertRaises(AccessError):
            self.foreign_group.with_user(self.guest).channel_join()
        self.assertNotIn(
            self.guest.partner_id, self.foreign_group.sudo().channel_partner_ids
        )

    @mute_logger("odoo.addons.base.models.ir_rule", "odoo.orm.models")
    def test_guest_cannot_join_a_foreign_support_conversation(self):
        vals = {"name": "Support of somebody else", "channel_type": "group"}
        if "support_key" in self.Channel._fields:
            vals["support_key"] = "partner:%s" % self.member.partner_id.id
        support = self.Channel.sudo().create(vals)
        support._add_members(partners=self.member.partner_id)
        with self.assertRaises(AccessError):
            self._self_join(support)

    @mute_logger("odoo.addons.base.models.ir_rule", "odoo.orm.models")
    def test_guest_cannot_join_a_foreign_chat(self):
        chat = self.Channel.with_user(self.employee)._get_or_create_chat(
            partners_to=self.member.partner_id.ids
        )
        # Core caps a chat at two members; whichever check fires first, the
        # guest must not end up seated.
        with self.assertRaises(Exception) as caught:
            self._self_join(chat)
        self.assertIsInstance(
            caught.exception, (AccessError, UserError, ValidationError)
        )
        self.assertNotIn(self.guest.partner_id, chat.sudo().channel_partner_ids)

    def test_guest_requests_its_own_support(self):
        if not hasattr(self.Channel, "_support_channel"):
            self.skipTest("website_pwa_chat is not installed")
        channel = self.Channel.with_user(self.guest)._support_channel()
        self.assertTrue(channel)
        self.assertIn(self.guest.partner_id, channel.sudo().channel_partner_ids)
        # Asking again finds the same conversation.
        self.assertEqual(self.Channel.with_user(self.guest)._support_channel(), channel)

    def test_guest_starts_a_direct_chat(self):
        chat = self.Channel.with_user(self.guest)._get_or_create_chat(
            partners_to=self.employee.partner_id.ids
        )
        self.assertEqual(chat.channel_type, "chat")
        self.assertEqual(
            chat.sudo().channel_partner_ids,
            self.guest.partner_id | self.employee.partner_id,
        )

    def test_guest_creates_a_group_and_invites_into_it(self):
        group = self.Channel.with_user(self.guest)._create_group(
            partners_to=self.employee.partner_id.ids
        )
        group.with_user(self.guest).add_members(partner_ids=self.member.partner_id.ids)
        self.assertEqual(
            group.sudo().channel_partner_ids,
            self.guest.partner_id | self.employee.partner_id | self.member.partner_id,
        )

    def test_guest_is_invited_into_a_group_by_someone_else(self):
        self.foreign_group.with_user(self.employee).add_members(
            partner_ids=self.guest.partner_id.ids
        )
        self.assertIn(
            self.guest.partner_id, self.foreign_group.sudo().channel_partner_ids
        )
