# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase, tagged
from odoo.tools import html2plaintext

from .common import CommunityModerationMixin


@tagged("post_install", "-at_install")
class TestCommunityHold(CommunityModerationMixin, TransactionCase):
    """The community branch of the hold: who is held, who is not.

    The engine's central invariant carries over unchanged: a held post
    leaves ZERO ``mail.message`` rows, because ``mail.message`` has no
    per-message visibility seam to hide a half-published one behind.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_community_moderation_fixtures()

    # ------------------------------------------------------------------
    # Community guests
    # ------------------------------------------------------------------

    def test_community_guest_is_held(self):
        result = self._post_as_user(
            self.channel_a, self.community_guest, "guest says hi"
        )
        self.assertFalse(
            result,
            "message_post must return an EMPTY recordset, never a half-built "
            "message",
        )
        self.assertEqual(result._name, "mail.message")
        self.assertFalse(self._channel_comments(self.channel_a))
        pending = self._pending_of(self.channel_a)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending.state, "pending")
        self.assertEqual(pending.partner_id, self.community_guest.partner_id)
        self.assertFalse(
            pending.guest_id,
            "a community guest is an internal USER, not a mail.guest: the "
            "row must be partner-authored",
        )

    def test_community_guest_not_held_when_switch_off(self):
        self.moderation_a.moderate_community_guests = False
        message = self._post_as_user(self.channel_a, self.community_guest)
        self.assertTrue(message)
        self.assertEqual(message.author_id, self.community_guest.partner_id)
        self.assertFalse(self._pending_of(self.channel_a))

    def test_engine_guest_switch_does_not_govern_community_guests(self):
        """`moderate_guests` is about mail.guest; turning it off must not
        open the door to community guests, whose switch is their own."""
        self.moderation_a.moderate_guests = False
        result = self._post_as_user(self.channel_a, self.community_guest)
        self.assertFalse(result)
        self.assertEqual(len(self._pending_of(self.channel_a)), 1)

    # ------------------------------------------------------------------
    # Community members
    # ------------------------------------------------------------------

    def test_new_member_is_held(self):
        result = self._post_as_user(self.channel_a, self.member, "member hi")
        self.assertFalse(result)
        self.assertFalse(self._channel_comments(self.channel_a))
        pending = self._pending_of(self.channel_a)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending.partner_id, self.member.partner_id)

    def test_member_not_held_when_switch_off(self):
        self.moderation_a.moderate_new_users = False
        message = self._post_as_user(self.channel_a, self.member)
        self.assertTrue(message)
        self.assertEqual(message.author_id, self.member.partner_id)
        self.assertFalse(self._pending_of(self.channel_a))

    def test_every_message_type_is_held_for_a_new_member(self):
        """The engine's regression lock, re-armed for the community branch:
        the type is attacker-supplied and must play no part in the decision.

        The whole selection is swept, READ from the field, so a type added
        by another module is covered the day it is installed.
        """
        message_types = self._message_type_values()
        self.assertIn("comment", message_types)
        for message_type in message_types:
            with self.subTest(message_type=message_type):
                result = self._post_as_user(
                    self.channel_a, self.member, "sweep", message_type=message_type
                )
                self.assertFalse(
                    result,
                    "message_type %r must not steer the community hold" % message_type,
                )
        self.assertFalse(
            self.env["mail.message"].search(
                [
                    ("model", "=", "discuss.channel"),
                    ("res_id", "=", self.channel_a.id),
                ]
            ),
            "a real hold leaves the channel at zero mail.message rows",
        )
        self.assertEqual(len(self._pending_of(self.channel_a)), len(message_types))

    def test_member_edit_of_published_message_reenters_queue(self):
        """The engine routes its edit gate through `_moderation_hold`, so a
        below-threshold member rewriting an approved message must land back
        in the queue -- with the published body withdrawn meanwhile."""
        self._post_as_user(self.channel_a, self.member, "first version")
        pending = self._pending_of(self.channel_a)
        self._approve(pending)
        message = pending.message_id
        self.assertTrue(message)
        self.channel_a.with_user(self.member).sudo()._message_update_content(
            message, body="<p>rewritten after approval</p>"
        )
        # Core's withdrawal leaves the "edited" marker span behind, so the
        # right assertion is "renders to no text", not "body is falsy".
        withdrawn = str(message.sudo().body)
        self.assertFalse(
            html2plaintext(withdrawn).strip(),
            "the published body must be withdrawn while the edit waits",
        )
        self.assertNotIn("first version", withdrawn)
        held_again = self._pending_of(self.channel_a).filtered(
            lambda row: row.state == "pending"
        )
        self.assertEqual(len(held_again), 1)
        self.assertIn("rewritten after approval", held_again.body)

    # ------------------------------------------------------------------
    # Everybody else
    # ------------------------------------------------------------------

    def test_plain_staff_is_never_held(self):
        message = self._post_as_user(self.channel_a, self.employee, "staff hi")
        self.assertTrue(message)
        self.assertFalse(self._pending_of(self.channel_a))

    def test_moderator_is_never_held_on_their_channel(self):
        """A moderator who is ALSO a community member is not held on the
        channel they moderate: holding them would only have them approve
        themselves, same outcome with extra rows."""
        self.moderator.write(
            {
                "group_ids": [
                    (
                        4,
                        self.env.ref("discuss_community.group_community_member").id,
                    )
                ]
            }
        )
        message = self._post_as_user(self.channel_a, self.moderator, "mod hi")
        self.assertTrue(message)
        self.assertFalse(self._pending_of(self.channel_a))

    def test_unmoderated_channel_is_untouched(self):
        for user in (self.community_guest, self.member):
            with self.subTest(user=user.login):
                message = self._post_as_user(self.channel_free, user, "free")
                self.assertTrue(message)
        self.assertFalse(self._pending_of(self.channel_free))

    def test_archived_moderation_does_not_hold_community_personas(self):
        self.moderation_a.active = False
        for user in (self.community_guest, self.member):
            with self.subTest(user=user.login):
                self.assertTrue(self._post_as_user(self.channel_a, user))
        self.assertFalse(self._pending_of(self.channel_a))

    # ------------------------------------------------------------------
    # Existing rows at install time
    # ------------------------------------------------------------------

    def test_seeded_zone_rows_carry_the_new_switches(self):
        """The four rows `discuss_channel_zone` seeds predate this module in
        the install order; the ORM's column initialisation must have given
        them the community defaults, or the zone channels would quietly stay
        open to the very personas Phase 2 exists to moderate."""
        for xmlid in (
            "discuss_channel_zone.moderation_canarias",
            "discuss_channel_zone.moderation_guanarteme",
            "discuss_channel_zone.moderation_tamaraceite",
            "discuss_channel_zone.moderation_lomolosfrailes",
        ):
            moderation = self.env.ref(xmlid)
            with self.subTest(xmlid=xmlid):
                self.assertTrue(moderation.moderate_community_guests)
                self.assertTrue(moderation.moderate_new_users)
                self.assertEqual(moderation.trust_threshold, 3)
