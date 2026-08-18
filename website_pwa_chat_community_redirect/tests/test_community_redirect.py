# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

from odoo.addons.website_pwa_chat.tests.common import HELD_BODY, WebsiteChatMixin

COMMUNITY_PATH = "/community"


@tagged("post_install", "-at_install")
class TestCommunityRedirect(WebsiteChatMixin, HttpCase):
    """The retirement, observed from outside like everything it retires.

    Reuses ``website_pwa_chat``'s own fixtures: the claims are about what
    happens to THAT module's routes and personas, so the scenario has to be
    its scenario, not a rebuilt one that could drift.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_chat_fixtures()

    def setUp(self):
        super().setUp()
        self.authenticate(None, None)

    def _assert_moved_to_community(self, response):
        self.assertEqual(
            response.status_code,
            301,
            "a retired page is Moved Permanently, not temporarily aside",
        )
        self.assertTrue(
            response.headers.get("Location", "").endswith(COMMUNITY_PATH),
            "the redirect must land on the /community door",
        )

    # ------------------------------------------------------------------
    # The community pages are retired
    # ------------------------------------------------------------------

    def test_the_channel_list_permanently_redirects_to_the_door(self):
        response = self.url_open("/chat", allow_redirects=False)
        self._assert_moved_to_community(response)

    def test_a_channel_page_permanently_redirects_to_the_door(self):
        response = self.url_open(
            "/chat/%s" % self.channel_general.id, allow_redirects=False
        )
        self._assert_moved_to_community(response)

    @mute_logger("odoo.http")
    def test_the_website_gate_survives_the_retirement(self):
        """217 microsites answered 404 and must keep answering 404.

        The redirect fires only where the standalone page used to be served;
        anywhere else it would turn a deliberate "this site does not serve
        the chat" into a live URL on every merchant's storefront.
        """
        self.websites.write({"chat_enabled": False})
        self.assertEqual(self.url_open("/chat").status_code, 404)
        self.assertEqual(
            self.url_open("/chat/%s" % self.channel_general.id).status_code,
            404,
        )

    # ------------------------------------------------------------------
    # The support feature is untouched
    # ------------------------------------------------------------------

    def test_the_support_page_still_serves_the_conversation(self):
        """/chat/soporte is support, not community: no redirect, a page.

        Asserted directly (redirects forbidden) and by its observable side
        effect -- a private conversation keyed to this visitor -- because a
        200 alone could be any page.
        """
        before = (
            self.env["discuss.channel"].sudo().search([("support_key", "!=", False)])
        )
        response = self.url_open("/chat/soporte", allow_redirects=False)
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="wrapwrap"', response.text)
        opened = (
            self.env["discuss.channel"].sudo().search([("support_key", "!=", False)])
        ) - before
        self.assertEqual(
            len(opened), 1, "the visit must still open one support conversation"
        )

    def test_the_jsonrpc_routes_still_answer_with_content(self):
        """The support window's live half rides these; they must not decay.

        Answered WITH the caller's held message, not just without error: an
        empty-but-200 answer is exactly what these routes return when their
        channel resolution breaks, so content is the only meaningful proof.
        """
        self._post_over_http(self.channel_general, self.visitor)
        messages = self.make_jsonrpc_request(
            "/website_pwa_chat/messages",
            {"channel_id": self.channel_general.id},
            cookies=self._cookies_for(self.visitor),
        )
        self.assertIn("messages", messages)
        pending = self.make_jsonrpc_request(
            "/website_pwa_chat/pending",
            {"channel_id": self.channel_general.id},
            cookies=self._cookies_for(self.visitor),
        )
        self.assertIn(HELD_BODY, pending["html"])

    def test_the_floating_button_still_points_at_support(self):
        """The bubble's URL helper is inherited untouched."""
        host = self.env["website"]._chat_host_website()
        self.assertEqual(host._chat_support_url(), "/chat/soporte")

    # ------------------------------------------------------------------
    # The menu entry points at the door
    # ------------------------------------------------------------------

    def test_the_host_website_menu_links_to_the_door_relatively(self):
        host = self.env["website"]._chat_host_website()
        self.assertEqual(host._chat_menu_url(), COMMUNITY_PATH)

    def test_the_menu_entry_renders_the_door_url(self):
        """The entry a visitor actually taps, read off a served page."""
        response = self.url_open(COMMUNITY_PATH)
        self.assertEqual(response.status_code, 200)
        self.assertIn("o_cc_chat_menu_link", response.text)
        self.assertIn('href="%s"' % COMMUNITY_PATH, response.text)

    def test_a_linked_website_gets_an_absolute_door_url(self):
        """The zone portals live on their own subdomains, and the sessions
        the door mints (guest, signup, /odoo) live on the host's domain --
        so the cross-subdomain shape of the /chat entry is kept as is."""
        host = self.env["website"]._chat_host_website()
        host.domain = "https://canariasconectada.example"
        zone = self.env["website"].create(
            {"name": "WPCR Zona", "chat_link_enabled": True}
        )
        self.assertEqual(
            zone._chat_menu_url(),
            "https://canariasconectada.example/community",
        )

    # ------------------------------------------------------------------
    # No persona loops between /chat and /community
    # ------------------------------------------------------------------

    def test_no_redirect_loop_for_any_persona(self):
        """/chat 301s to /community; /community must never answer /chat.

        Followed to the END of the chain for the personas /community
        distinguishes: anonymous and portal must come to rest on the card
        (a loop would raise TooManyRedirects in the client long before any
        assertion), and an internal session must be handed on to /odoo,
        never back towards /chat.
        """
        for label, login in (("anonymous", None), ("portal", "dcz_merchant")):
            with self.subTest(persona=label):
                self.authenticate(login, login)
                self._forget_guest_cookie()
                response = self.url_open("/chat")
                self.assertEqual(response.status_code, 200)
                self.assertTrue(
                    response.url.rstrip("/").endswith(COMMUNITY_PATH),
                    "%s must come to rest on the /community card" % label,
                )

        with self.subTest(persona="internal"):
            self.authenticate("dcz_staff", "dcz_staff")
            self._forget_guest_cookie()
            first = self.url_open("/chat", allow_redirects=False)
            self._assert_moved_to_community(first)
            second = self.url_open(COMMUNITY_PATH, allow_redirects=False)
            self.assertTrue(
                second.headers.get("Location", "").endswith("/odoo"),
                "an internal session leaves the loop for the backend",
            )

    def test_the_portal_card_offers_no_dead_doors(self):
        """The card a portal session lands on renders and says why.

        The specific regression this forbids: /community answering the old
        Phase 1 redirect to /chat, which this module has just turned into a
        301 back to /community.
        """
        self.authenticate("dcz_merchant", "dcz_merchant")
        self._forget_guest_cookie()
        response = self.url_open(COMMUNITY_PATH, allow_redirects=False)
        self.assertEqual(response.status_code, 200)
        self.assertIn("o_cc_portal_note", response.text)
