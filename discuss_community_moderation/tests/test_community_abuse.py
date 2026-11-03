# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import HttpCase, tagged

from .common import CommunityModerationMixin


@tagged("post_install", "-at_install")
class TestCommunityAbuse(CommunityModerationMixin, HttpCase):
    """Attack through the REAL public route, logged in as the moderated one.

    Community personas differ from the engine's in one way that matters
    here: they have a password, so the abuser arrives with an authenticated
    session instead of a guest cookie. `/mail/message/post` is the same
    door, `request.update_context(**context)` still hands them every context
    key, and `message_type` still rides `post_data` unfiltered -- so the
    engine's abuse patterns are re-run with the new personas.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_community_moderation_fixtures()

    def _post_over_http(
        self, channel, body="abuse", context=None, message_type="comment"
    ):
        params = {
            "thread_model": "discuss.channel",
            "thread_id": channel.id,
            "post_data": {
                "body": body,
                "message_type": message_type,
                "subtype_xmlid": "mail.mt_comment",
            },
        }
        if context is not None:
            params["context"] = context
        return self.make_jsonrpc_request("/mail/message/post", params)

    def test_member_context_flags_cannot_bypass(self):
        """No context key may open a service door: the poster controls the
        whole context of the route, so any such door would be theirs."""
        self.authenticate("dccm_member", "dccm_member_pwd")
        result = self._post_over_http(
            self.channel_a,
            body="bypass attempt",
            context={
                "moderation_bypass": True,
                "discuss_channel_moderation_skip": True,
                "skip_moderation": True,
                "community_trusted": True,
            },
        )
        self.assertFalse(
            result["message_id"],
            "the route must report that nothing was published",
        )
        self.assertFalse(self._channel_comments(self.channel_a))
        pending = self._pending_of(self.channel_a, self.member)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending.state, "pending")

    def test_no_message_type_survives_the_route_for_a_member(self):
        """The sweep, over HTTP: `message_type` is attacker-supplied all the
        way to `message_post` and must not steer the community hold either."""
        self.authenticate("dccm_member", "dccm_member_pwd")
        message_types = self._message_type_values()
        for message_type in message_types:
            with self.subTest(message_type=message_type):
                result = self._post_over_http(
                    self.channel_a,
                    body="<b>abuse %s</b>" % message_type,
                    message_type=message_type,
                )
                self.assertFalse(result["message_id"])
        self.assertFalse(
            self.env["mail.message"].search(
                [
                    ("model", "=", "discuss.channel"),
                    ("res_id", "=", self.channel_a.id),
                ]
            )
        )
        self.assertEqual(
            len(self._pending_of(self.channel_a, self.member)),
            len(message_types),
        )

    def test_community_guest_raw_route_is_held(self):
        self.authenticate(self.community_guest.login, "dccm_cguest_pwd")
        result = self._post_over_http(self.channel_a, body="raw guest post")
        self.assertFalse(result["message_id"])
        self.assertFalse(self._channel_comments(self.channel_a))
        self.assertEqual(len(self._pending_of(self.channel_a, self.community_guest)), 1)

    def test_trusted_member_publishes_over_the_route(self):
        """Positive control: the route works, and what was stopping the
        member was the probation, nothing else."""
        self._earn_trust(self.channel_a, self.member, 3)
        self.authenticate("dccm_member", "dccm_member_pwd")
        result = self._post_over_http(self.channel_a, body="trusted now")
        self.assertTrue(result["message_id"])
        comments = self._channel_comments(self.channel_a)
        # Three approved probation messages plus this direct one.
        self.assertEqual(len(comments), 4)
        self.assertIn(
            result["message_id"],
            comments.ids,
            "the trusted post must be a real, directly published comment",
        )
