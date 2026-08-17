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

    def _enable_link(self):
        """Turn the button on WITHOUT poisoning the next test.

        The layout caches rendered fragments (`t-cache`), and the registry
        cache outlives this test's rollback: a header rendered here with the
        Comunidad entry in it would be served verbatim to the next test,
        which asserts the entry is absent. Cleared going in (this test must
        not read the off-state header either) and going out.
        """
        self.websites.write({"chat_link_enabled": True})
        self.registry.clear_cache("templates")
        self.addCleanup(self.registry.clear_cache, "templates")

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
    # The floating window
    # ------------------------------------------------------------------

    def test_the_page_carries_the_window_and_a_lazy_frame(self):
        """The button's markup ships on every page; the conversation does not.

        ``data-src`` and no ``src`` is the load-bearing half of this feature:
        /chat/soporte opens a conversation for whoever knocks, so an iframe
        that loaded eagerly would create one empty support conversation per
        page view, platform-wide.
        """
        # The button rides on the link opt-in, which the fixtures leave off
        # because launch left it off; the window is only reachable through it.
        self._enable_link()
        self._forget_guest_cookie()
        before = self._support_channels()

        response = self.url_open("/")

        self.assertIn("o_cc_chat_window", response.text)
        self.assertIn('data-src="/chat/soporte?frame=1"', response.text)
        self.assertNotIn('src="/chat/soporte?frame=1"', response.text.replace("data-src", ""))
        self.assertEqual(
            self._support_channels(),
            before,
            "rendering a page must not open a support conversation",
        )

    def test_the_framed_page_strips_the_chrome_and_the_recursion(self):
        # With the link off the button is absent everywhere and the recursion
        # assertion below would pass without meaning anything.
        self._enable_link()
        self._forget_guest_cookie()
        response = self.url_open(SUPPORT_URL + "?frame=1")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('<header id="top"', response.text)
        self.assertNotIn(
            "o_cc_chat_fab",
            response.text,
            "a support button inside the support window would recurse",
        )
        self.assertNotIn(
            "Todos los canales",
            response.text,
            "the channel list is a full page and has no business in the window",
        )

    def test_the_full_page_still_has_its_chrome(self):
        self._enable_link()
        self._forget_guest_cookie()
        response = self.url_open(SUPPORT_URL)

        self.assertIn('<header id="top"', response.text)
        self.assertIn("o_cc_chat_fab", response.text)

    def test_the_identify_card_invites_the_visitor_to_register(self):
        self._forget_guest_cookie()
        response = self.url_open(SUPPORT_URL)

        self.assertIn("o_cc_chat_identify_signup", response.text)
        self.assertIn("Crear mi cuenta", response.text)
        self.assertIn("Ya tengo cuenta", response.text)

    def test_a_frame_value_other_than_one_means_the_full_page(self):
        """bool() on a query string would call "0" true; the visitor means no."""
        self._enable_link()
        self._forget_guest_cookie()
        response = self.url_open(SUPPORT_URL + "?frame=0")

        self.assertIn('<header id="top"', response.text)
        self.assertIn("o_cc_chat_fab", response.text)

    def test_a_linked_site_frames_the_host_site_cross_subdomain(self):
        """The branch the window was built FOR: the three zone portals.

        They do not serve /chat/soporte themselves, so their iframe has to
        point at the host website's own domain, frame flag included.
        """
        self._enable_link()
        host = self.env["website"]._chat_host_website()
        host.domain = "https://portal.example"
        zone = self.env["website"].create(
            {
                "name": "WPC Zona Ventana",
                "chat_enabled": False,
                "chat_link_enabled": True,
            }
        )

        self.assertEqual(
            zone._chat_support_url() + "?frame=1",
            "https://portal.example/chat/soporte?frame=1",
            "a relative URL on a zone portal would 404 on its own subdomain",
        )

    def test_the_support_page_sends_no_frame_blocking_header(self):
        """The executable form of the claim the window rests on.

        The day a hardening pass adds X-Frame-Options or frame-ancestors to
        this route, the button silently dies on every site that frames the
        portal cross-subdomain -- this is the test that says so out loud.
        """
        self._forget_guest_cookie()
        response = self.url_open(SUPPORT_URL + "?frame=1")

        self.assertNotIn("X-Frame-Options", response.headers)
        self.assertNotIn(
            "frame-ancestors",
            response.headers.get("Content-Security-Policy", ""),
        )

    def test_identifying_from_the_full_page_stays_on_the_full_page(self):
        """The pre-existing branch, asserted for the first time.

        A regression that always appended ?frame=1 would otherwise pass CI.
        """
        self._forget_guest_cookie()
        page = self.url_open(SUPPORT_URL)
        csrf = page.text.split('name="csrf_token"')[1].split('value="')[1]
        csrf = csrf.split('"')[0]

        response = self.url_open(
            "/chat/soporte/identificarme",
            data={"name": "Vecina de prueba", "csrf_token": csrf},
            allow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers["Location"].endswith("/chat/soporte"))

    def test_identifying_from_the_window_lands_back_in_the_window(self):
        self._forget_guest_cookie()
        page = self.url_open(SUPPORT_URL + "?frame=1")
        csrf = page.text.split('name="csrf_token"')[1].split('value="')[1]
        csrf = csrf.split('"')[0]

        response = self.url_open(
            "/chat/soporte/identificarme",
            data={"name": "Vecina de prueba", "frame": "1", "csrf_token": csrf},
            allow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertTrue(
            response.headers["Location"].endswith("/chat/soporte?frame=1"),
            "posted from the window, the visitor must land back in the window",
        )

    # ------------------------------------------------------------------
    # The Discuss sidebar
    # ------------------------------------------------------------------

    def test_the_store_flags_support_channels_for_the_sidebar(self):
        """The one bit the Soporte category in Discuss keys on.

        A boolean, not the key: the sidebar only files the conversation, and
        the key encodes partner and guest ids no client needs.
        """
        from odoo.addons.mail.tools.discuss import Store

        self._forget_guest_cookie()
        self.url_open(SUPPORT_URL)
        support = self._support_channels()[0]
        ordinary = self.channel_general

        rows = (
            Store()
            .add(support + ordinary)
            .get_result()
            .get("discuss.channel", [])
        )
        by_id = {row["id"]: row for row in rows}
        self.assertTrue(by_id[support.id]["is_support_channel"])
        self.assertFalse(by_id[ordinary.id]["is_support_channel"])

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
