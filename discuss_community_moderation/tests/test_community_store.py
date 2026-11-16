# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase, tagged

from odoo.addons.discuss_channel_moderation.models.discuss_channel_pending_message import (
    BUS_AUTHOR_STATUS,
)
from odoo.addons.mail.tools.discuss import Store

from .common import CommunityModerationMixin


@tagged("post_install", "-at_install")
class TestCommunityStore(CommunityModerationMixin, TransactionCase):
    """What the Discuss client is SERVED, and to whom.

    Mirrors `test_moderation_visibility`'s discipline: a held message that
    leaks to a third party through the store attr would undo the hold at the
    read side, so every test here is phrased as "who reads what", never as
    "what the method returns for the right user".
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_community_moderation_fixtures()

    def _own_store(self, channel, user, guest=None):
        channel = channel.with_user(user)
        if guest is not None:
            channel = channel.with_context(guest=guest)
        return channel._community_own_pending_store()

    def test_store_contains_only_the_callers_rows(self):
        self._post_as_user(self.channel_a, self.member, "mine")
        self._post_as_user(self.channel_a, self.member_b, "theirs")
        entries = self._own_store(self.channel_a, self.member)
        self.assertEqual(len(entries), 1)
        self.assertIn("mine", entries[0]["body"])
        self.assertEqual(entries[0]["state"], "pending")
        other_entries = self._own_store(self.channel_a, self.member_b)
        self.assertEqual(len(other_entries), 1)
        self.assertIn("theirs", other_entries[0]["body"])

    def test_store_never_mixes_channels(self):
        self._post_as_user(self.channel_a, self.member, "in a")
        self._post_as_user(self.channel_b, self.member, "in b")
        entries = self._own_store(self.channel_a, self.member)
        self.assertEqual(len(entries), 1)
        self.assertIn("in a", entries[0]["body"])

    def test_public_session_is_served_nothing(self):
        """The cookie-less public session's holds are authored by the ONE
        shared public partner; matching on it would show every anonymous
        visitor everybody else's queue. `_get_current_persona` returns an
        EMPTY partner for public sessions, which makes the guard structural
        -- pinned here so nobody replaces it with `env.user.partner_id`."""
        self._post_as_user(self.channel_a, self.member, "held")
        self.assertEqual(self._own_store(self.channel_a, self.public_user), [])

    def test_mail_guest_reads_only_their_own_rows(self):
        guest_one, guest_two = self.env["mail.guest"].create(
            [{"name": "Store Guest One"}, {"name": "Store Guest Two"}]
        )
        for guest, body in ((guest_one, "from one"), (guest_two, "from two")):
            (
                self.channel_a.with_user(self.public_user)
                .sudo()
                .with_context(guest=guest)
                .message_post(
                    body=body,
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment",
                )
            )
        entries = self._own_store(self.channel_a, self.public_user, guest=guest_one)
        self.assertEqual(len(entries), 1)
        self.assertIn("from one", entries[0]["body"])

    def test_staff_is_served_an_empty_list(self):
        """The community gate on the attr is a cost guard, and this pins its
        one observable behaviour: staff sessions get [] without a queue
        lookup mattering to them."""
        self._post_as_user(self.channel_a, self.member, "held")
        self.assertEqual(self._own_store(self.channel_a, self.employee), [])

    def test_decided_rows_do_not_travel_in_the_store(self):
        """Approved rows become real messages the client already renders;
        rejected rows are announced once over the bus. Replaying either on
        every reload would be noise, so only pending rows travel."""
        self._post_as_user(self.channel_a, self.member, "will be approved")
        self._approve(self._pending_of(self.channel_a, self.member))
        self._post_as_user(self.channel_a, self.member, "will be rejected")
        self._reject(
            self._pending_of(self.channel_a, self.member).filtered(
                lambda row: row.state == "pending"
            ),
            reason="not this",
        )
        self.assertEqual(self._own_store(self.channel_a, self.member), [])

    def test_store_serialization_carries_the_attr(self):
        """End to end through the real `Store` machinery, not just the
        helper: the channel payload a community member's client receives
        must contain their pending rows under `cc_pending_messages`."""
        self._post_as_user(self.channel_a, self.member, "serialized")
        result = Store().add(self.channel_a.with_user(self.member)).get_result()
        channels = result.get("discuss.channel", [])
        self.assertEqual(len(channels), 1)
        entries = channels[0].get("cc_pending_messages")
        self.assertEqual(len(entries), 1)
        self.assertIn("serialized", entries[0]["body"])

    # ------------------------------------------------------------------
    # The author's bus notifications
    # ------------------------------------------------------------------

    def test_hold_notifies_the_author_with_the_body(self):
        self._post_as_user(self.channel_a, self.member, "notify me")
        payloads = self._bus_payloads(self.member.partner_id, BUS_AUTHOR_STATUS)
        self.assertEqual(len(payloads), 1)
        payload = payloads[0]
        self.assertEqual(payload["state"], "pending")
        self.assertEqual(payload["channel_id"], self.channel_a.id)
        self.assertIn(
            "notify me",
            payload["body"],
            "the placeholder needs the body: the engine's minimal payload "
            "is extended, not replaced",
        )

    def test_approval_notifies_the_author(self):
        self._post_as_user(self.channel_a, self.member, "approve me")
        pending = self._pending_of(self.channel_a, self.member)
        self._approve(pending)
        payloads = self._bus_payloads(self.member.partner_id, BUS_AUTHOR_STATUS)
        approved = [p for p in payloads if p["state"] == "approved"]
        self.assertEqual(len(approved), 1)
        self.assertEqual(approved[0]["message_id"], pending.message_id.id)

    def test_rejection_notifies_the_author_with_the_reason(self):
        self._post_as_user(self.channel_a, self.member, "reject me")
        pending = self._pending_of(self.channel_a, self.member)
        self._reject(pending, reason="off-topic")
        payloads = self._bus_payloads(self.member.partner_id, BUS_AUTHOR_STATUS)
        rejected = [p for p in payloads if p["state"] == "rejected"]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["rejection_reason"], "off-topic")
        self.assertIn("reject me", rejected[0]["body"])

    def test_status_notifications_reach_nobody_else(self):
        """The author's own words travel on the author's own bus channel and
        no other partner's -- the payload growing a body makes this worth
        pinning."""
        self._post_as_user(self.channel_a, self.member, "private words")
        for partner in (
            self.member_b.partner_id,
            self.employee.partner_id,
        ):
            self.assertEqual(
                self._bus_payloads(partner, BUS_AUTHOR_STATUS),
                [],
                "no third party may receive the author's status payload",
            )
