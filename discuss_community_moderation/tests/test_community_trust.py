# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase, tagged

from .common import CommunityModerationMixin


@tagged("post_install", "-at_install")
class TestCommunityTrust(CommunityModerationMixin, TransactionCase):
    """The probation: held until N approvals, per channel, member-only.

    Trust is nothing but a COUNT over the engine's own decided rows -- an
    approved `discuss.channel.pending.message` already records who approved
    and when -- so every test here manufactures its evidence through the real
    approve/reject flow, never by writing states directly.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_community_moderation_fixtures()

    def test_member_passes_after_threshold(self):
        self.assertEqual(self.moderation_a.trust_threshold, 3)
        self._earn_trust(self.channel_a, self.member, 3)
        message = self._post_as_user(self.channel_a, self.member, "free at last")
        self.assertTrue(
            message,
            "three approvals on this channel must end the probation here",
        )
        self.assertEqual(message.author_id, self.member.partner_id)
        self.assertEqual(
            self.Pending.search_count(
                [
                    ("channel_id", "=", self.channel_a.id),
                    ("state", "=", "pending"),
                ]
            ),
            0,
        )

    def test_below_threshold_is_still_held(self):
        self._earn_trust(self.channel_a, self.member, 2)
        result = self._post_as_user(self.channel_a, self.member, "not yet")
        self.assertFalse(result, "two of three approvals is still probation")
        self.assertEqual(
            len(
                self._pending_of(self.channel_a, self.member).filtered(
                    lambda row: row.state == "pending"
                )
            ),
            1,
        )

    def test_rejected_rows_do_not_count(self):
        """Trust is APPROVED messages, not messages that went through the
        queue: three rejections must leave the author exactly where they
        started."""
        for index in range(3):
            self._post_as_user(self.channel_a, self.member, "spam %s" % index)
            pending = self._pending_of(self.channel_a, self.member).filtered(
                lambda row: row.state == "pending"
            )
            self._reject(pending, reason="no")
        result = self._post_as_user(self.channel_a, self.member, "again")
        self.assertFalse(result)

    def test_trust_is_per_channel(self):
        """Consistent with the engine's scoping: the switch row, the quota
        and the moderators are all per channel, and so is the probation."""
        self._earn_trust(self.channel_a, self.member, 3)
        result = self._post_as_user(self.channel_b, self.member, "new room")
        self.assertFalse(
            result,
            "trust earned on channel A says nothing about channel B",
        )
        self.assertEqual(len(self._pending_of(self.channel_b, self.member)), 1)

    def test_threshold_zero_disables_probation(self):
        self.moderation_a.trust_threshold = 0
        message = self._post_as_user(self.channel_a, self.member, "instant")
        self.assertTrue(message)
        self.assertFalse(self._pending_of(self.channel_a))

    def test_raising_the_threshold_reopens_probation(self):
        """The count is evaluated at post time against the CURRENT threshold:
        a moderator who raises the bar puts everybody under it back on
        probation, which is the entire point of raising it."""
        self._earn_trust(self.channel_a, self.member, 3)
        self.assertTrue(self._post_as_user(self.channel_a, self.member))
        self.moderation_a.trust_threshold = 5
        result = self._post_as_user(self.channel_a, self.member, "held again")
        self.assertFalse(result)

    def test_community_guest_never_earns_trust(self):
        """A community guest holds `group_community_member` too (the doors
        hand both populations the same groups). The guest flag must decide
        FIRST, or three approvals would walk an anonymous throwaway account
        out of moderation for good."""
        self._earn_trust(self.channel_a, self.community_guest, 3)
        result = self._post_as_user(self.channel_a, self.community_guest, "still me")
        self.assertFalse(
            result,
            "approvals must never end a community guest's moderation",
        )

    def test_other_members_trust_is_not_borrowed(self):
        self._earn_trust(self.channel_a, self.member, 3)
        result = self._post_as_user(self.channel_a, self.member_b, "newcomer")
        self.assertFalse(result, "trust belongs to the author, not to the channel")
