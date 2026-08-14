# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import HttpCase, tagged

from .common import WebsiteChatMixin

SUPPORT_URL = "/chat/soporte"

# The one sentence the card on the channel list promises. Asserted as text
# rather than as a class because it is what a visitor reads and acts on.
SUPPORT_CALL = "Hablar con soporte"


@tagged("post_install", "-at_install")
class TestSupportChat(WebsiteChatMixin, HttpCase):
    """The private line to support: who gets one, and who cannot read it.

    Exercised over HTTP for the same reason as the rest of this suite. The
    whole feature is a statement about personas — this visitor, that visitor,
    the agent — and from the ORM with ``sudo()`` every one of them looks the
    same.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_chat_fixtures()
        cls.support_group = cls.env.ref("website_pwa_chat.group_support_agent")
        cls.agent = cls._make_agent("wpc_support", "WPC Support Agent")

    @classmethod
    def _make_agent(cls, login, name):
        """Appoint somebody to support the way this platform appoints anybody.

        NOT by writing ``group_ids`` on the user. ``base_user_role`` is
        installed, and it re-derives a user's groups from their roles inside
        every ``res.users.write`` — so a group ticked on the user form saves
        without complaint and is gone by the next write. The first draft of
        this suite did exactly that and the group finished the run with no
        members at all, which is how the platform's own support role came to
        exist (``f41_support_role``).

        Granting through a role is therefore not a test convenience; it is the
        only grant that lasts, and the test asserts against the real gesture.
        """
        user = cls.env["res.users"].create(
            {"name": name, "login": login, "email": "%s@example.com" % login}
        )
        role = cls.env["res.users.role"].create({"name": "Support: %s" % login})
        role.write(
            {
                "implied_ids": [
                    (4, cls.env.ref("base.group_user").id),
                    (4, cls.support_group.id),
                ],
                "line_ids": [(0, 0, {"user_id": user.id})],
            }
        )
        return user

    def _support_channels(self):
        return (
            self.env["discuss.channel"].sudo().search([("support_key", "!=", False)])
        )

    # ------------------------------------------------------------------
    # Getting one
    # ------------------------------------------------------------------

    def test_the_channel_list_offers_the_support_line(self):
        self._forget_guest_cookie()
        response = self.url_open("/chat")
        self.assertIn(SUPPORT_CALL, response.text)
        self.assertIn(SUPPORT_URL, response.text)

    def test_an_anonymous_visitor_is_given_a_conversation_of_their_own(self):
        self._forget_guest_cookie()
        before = self._support_channels()

        response = self.url_open(SUPPORT_URL)

        self.assertEqual(response.status_code, 200)
        opened = self._support_channels() - before
        self.assertEqual(len(opened), 1, "one visitor, one conversation")
        self.assertTrue(opened.support_key.startswith("guest-"))

    def test_coming_back_reopens_the_same_conversation(self):
        self._forget_guest_cookie()
        self.url_open(SUPPORT_URL)
        after_first = self._support_channels()

        self.url_open(SUPPORT_URL)

        self.assertEqual(
            self._support_channels(),
            after_first,
            "the same visitor must not accumulate conversations",
        )

    def test_a_signed_in_visitor_is_keyed_on_their_account(self):
        self.authenticate(self.resident.login, self.resident.login)
        self.url_open(SUPPORT_URL)

        self.assertTrue(
            self._support_channels().filtered(
                lambda c: c.support_key == "partner-%s" % self.resident.partner_id.id
            ),
            "an account keeps its conversation across devices, a cookie does not",
        )

    # ------------------------------------------------------------------
    # Keeping it private
    # ------------------------------------------------------------------

    def test_the_support_conversation_is_never_on_the_public_list(self):
        self._forget_guest_cookie()
        self.url_open(SUPPORT_URL)
        channel = self._support_channels()[0]

        self._forget_guest_cookie()
        listed = self.url_open("/chat")

        self.assertNotIn("/chat/%s" % channel.id, listed.text)
        self.assertFalse(
            channel.website_chat_published,
            "publishing it would put a private conversation on a public page",
        )

    def test_another_visitor_cannot_open_it(self):
        self._forget_guest_cookie()
        self.url_open(SUPPORT_URL)
        channel = self._support_channels()[0]

        # A second visitor, with their own identity and their own conversation.
        self._forget_guest_cookie()
        self.url_open(SUPPORT_URL)

        response = self.url_open("/chat/%s" % channel.id)
        self.assertEqual(
            response.status_code,
            404,
            "somebody else's support conversation must not exist for me",
        )

    def test_an_anonymous_caller_cannot_read_its_messages(self):
        self._forget_guest_cookie()
        self.url_open(SUPPORT_URL)
        channel = self._support_channels()[0]

        self._forget_guest_cookie()
        result = self.make_jsonrpc_request(
            "/website_pwa_chat/messages", {"channel_id": channel.id}
        )

        self.assertEqual(
            result["messages"],
            [],
            "the catch-up route reaches the same channels the page does, no more",
        )

    def test_it_is_a_group_and_not_a_channel(self):
        """The single value the whole privacy of this feature rests on.

        ``ir_rule_discuss_channel_all`` only asks ``is_member`` for types other
        than ``channel``; for ``channel`` it asks about ``group_public_id``,
        and a private-looking channel with no group is readable by everyone.
        """
        self._forget_guest_cookie()
        self.url_open(SUPPORT_URL)

        self.assertEqual(self._support_channels()[0].channel_type, "group")

    # ------------------------------------------------------------------
    # Being answered
    # ------------------------------------------------------------------

    def test_the_agent_is_seated_when_the_conversation_opens(self):
        """Exercised through the model, not through the page, on purpose.

        ``_support_channel`` is the method the controller calls, so this is
        the same code path the visitor triggers — but an agent appointed
        inside the test transaction is not visible to the request thread,
        which resolves group membership through the registry's own cache. The
        HTTP variant of this assertion failed for that reason and only that
        reason: repeated against a committed agent on a running server, the
        conversation opened with the agent seated.

        The rest of this suite keeps its HTTP coverage, because what it
        asserts — who gets a conversation, who is refused one — does not
        depend on a group appointed mid-transaction.
        """
        guest = (
            self.env["mail.guest"]
            .sudo()
            .create({"name": "Visitante de prueba", "timezone": "Atlantic/Canary"})
        )
        channel = (
            self.env["discuss.channel"]
            .with_user(self.env.ref("base.public_user"))
            .with_context(guest=guest)
            ._support_channel()
        )

        self.assertTrue(channel, "a visitor with an identity gets a conversation")
        self.assertIn(
            self.agent.partner_id,
            channel.sudo().channel_member_ids.partner_id,
            "an unanswered queue is the same as no support at all",
        )

    def test_an_agent_appointed_later_joins_the_conversations_already_waiting(self):
        self._forget_guest_cookie()
        self.url_open(SUPPORT_URL)
        channel = self._support_channels()[0]

        latecomer = self._make_agent("wpc_late", "WPC Late Agent")
        self.assertNotIn(latecomer.partner_id, channel.channel_member_ids.partner_id)

        self.env["discuss.channel"]._support_sync_agents()

        self.assertIn(
            latecomer.partner_id,
            channel.channel_member_ids.partner_id,
            "granting the group has to be enough to start answering",
        )
