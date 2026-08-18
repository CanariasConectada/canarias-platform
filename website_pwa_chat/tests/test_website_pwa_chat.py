# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

from .common import HELD_BODY, OTHER_HELD_BODY, UNDER_REVIEW, WebsiteChatMixin


@tagged("post_install", "-at_install")
class TestWebsiteChat(WebsiteChatMixin, HttpCase):
    """The chat page, exercised where its value is: inside a real request.

    Every claim this module makes is a claim about what a specific persona is
    served over HTTP -- which channels are on their list, whose held message
    they can read, whether the page is part of the app. None of that is
    observable from the ORM, where ``sudo()`` and the test user hide exactly
    the differences under test.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_chat_fixtures()

    def setUp(self):
        """Open the anonymous session before the first request.

        ``authenticate(None, None)`` does not log anybody in; it creates the
        session and plants its cookie. It also REPLACES ``self.opener``
        (``odoo/tests/common.py:2358``), so doing it mid-test would throw away
        cookies already set -- which is why it belongs here and not in a
        helper.
        """
        super().setUp()
        self.authenticate(None, None)

    # ------------------------------------------------------------------
    # The page is part of the app
    # ------------------------------------------------------------------

    def test_chat_page_is_served_inside_the_website_layout(self):
        """THE reason this module exists rather than a link to core's page.

        ``rel="manifest"`` is the proof, and it is not decoration: the link is
        injected by ``website_pwa`` into ``website.layout`` only. Core's public
        Discuss page renders ``mail.discuss_public_channel_template``, a
        standalone ``<html>`` with its own ``<head>``, so a chat built on it
        would answer 200 to a naive test and still drop the visitor out of the
        installed app. ``wrapwrap`` is checked alongside because a manifest tag
        could in principle be injected anywhere; the two together say "this is
        the website layout".
        """
        response = self._get_index()
        self.assertEqual(response.status_code, 200)
        self.assertIn('rel="manifest"', response.text)
        self.assertIn("/website_pwa/manifest.webmanifest", response.text)
        self.assertIn('id="wrapwrap"', response.text)

    def test_channel_page_is_served_inside_the_website_layout(self):
        """Same property for the page a visitor actually spends time on.

        Asserted separately from the index because they are two templates and
        only one of them was checked the first time round.
        """
        response = self._get_channel(self.channel_general, self.visitor)
        self.assertEqual(response.status_code, 200)
        self.assertIn('rel="manifest"', response.text)
        self.assertIn('id="wrapwrap"', response.text)

    # ------------------------------------------------------------------
    # The list shows what the visitor may really open
    # ------------------------------------------------------------------

    def test_visitor_is_offered_the_general_channel_only(self):
        """The list is the record rule's answer, not this module's.

        The failure this forbids is not a security hole -- the zone channels
        are closed either way -- it is a link that 404s. Offering a visitor a
        door that will not open is how a product teaches people it is broken,
        so the assertion is exact absence of the three, not just presence of
        the one.
        """
        response = self._get_index()
        self.assertEqual(response.status_code, 200)
        self.assertRegex(response.text, self._channel_link(self.channel_general))
        for channel in (
            self.channel_guanarteme,
            self.channel_tamaraceite,
            self.channel_lomo,
        ):
            with self.subTest(channel=channel.name):
                self.assertNotRegex(response.text, self._channel_link(channel))

    def test_registered_user_is_offered_all_four_channels(self):
        """The control without which the test above proves nothing.

        A list that is empty for everybody would also hide the three zone
        channels from a visitor. This is what distinguishes "closed to
        anonymous" from "broken for all", and it uses a PORTAL user -- who has
        no ``base.group_user`` -- because that is the case a naive gate on
        ``base.group_portal`` or on ``base.group_user`` would each get wrong.
        """
        self.authenticate("dcz_merchant", "dcz_merchant")
        self._forget_guest_cookie()
        response = self.url_open("/chat")
        self.assertEqual(response.status_code, 200)
        for channel in self.managed_channels:
            with self.subTest(channel=channel.name):
                self.assertRegex(response.text, self._channel_link(channel))

    def test_an_unpublished_channel_is_not_offered_to_a_user_who_can_read_it(self):
        """The publication flag has to be the thing that decides, not the ACL.

        Both tests above pass with the ``website_chat_published`` filter DELETED
        from ``_website_chat_channels``: the visitor's list is already trimmed
        by the record rule, and the registered-user list only asserts that the
        four managed channels are PRESENT. Nothing was left asking the question
        the flag exists to answer, so removing the filter -- publishing every
        channel of the database on a public page -- broke no test.

        ``mail.channel_all_employees`` is the realistic case and the reason the
        module has the flag at all: core seeds it, every internal user may read
        it, and nobody ever decided it should appear on the website. Asserted
        with a logged-in INTERNAL user, because for a portal user or a visitor
        the record rule would hide it anyway and the test would pass without
        the filter existing.

        The general channel is asserted alongside so a list that renders
        nothing at all -- the other way to make the first assertion true --
        cannot be mistaken for a pass.
        """
        internal_channel = self.env.ref("mail.channel_all_employees")
        self.assertFalse(
            internal_channel.website_chat_published,
            "nobody published core's employee channel; that is the point",
        )
        self.assertTrue(
            self.env["discuss.channel"]
            .with_user(self.staff)
            .search([("id", "=", internal_channel.id)]),
            "the test is worthless unless this user really CAN read the channel: "
            "the record rule alone would hide it and prove nothing",
        )

        self.authenticate("dcz_staff", "dcz_staff")
        self._forget_guest_cookie()
        response = self.url_open("/chat")

        self.assertEqual(response.status_code, 200)
        self.assertNotRegex(
            response.text,
            self._channel_link(internal_channel),
            "an unpublished channel must never reach the community page",
        )
        self.assertRegex(
            response.text,
            self._channel_link(self.channel_general),
            "and the published one still has to be there",
        )

    @mute_logger("odoo.http")
    def test_a_zone_channel_page_does_not_exist_for_a_visitor(self):
        """Not listing it is not the same as not serving it.

        The list is what the visitor sees; this is what happens when they type
        the URL anyway. Both go through the same ``search()``, which is the
        point: there is one gate, not a display filter with a hole behind it.
        """
        response = self._get_channel(self.channel_guanarteme, self.visitor)
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------------
    # The website switch
    # ------------------------------------------------------------------

    @mute_logger("odoo.http")
    def test_chat_is_not_served_by_a_website_that_did_not_ask_for_it(self):
        """The mechanism that keeps 217 microsites out of this.

        The channels belong to the whole platform, so a merchant's site
        serving them would put another merchant's conversation on their
        storefront. 404 rather than an empty page: a page that renders would
        leave a live URL and a dead menu entry behind on every site.
        """
        self.websites.write({"chat_enabled": False})
        self.assertEqual(self.url_open("/chat").status_code, 404)
        self.assertEqual(self._get_channel(self.channel_general).status_code, 404)

    # ------------------------------------------------------------------
    # The way in
    # ------------------------------------------------------------------

    def test_serving_the_chat_does_not_advertise_it(self):
        """Serving a route and advertising it are separate decisions.

        The platform launched with ``/chat`` live and the navbars mirroring
        production, which has no Comunidad entry (user decision 2026-08-11).
        The fixtures enable ``chat_enabled`` everywhere and leave
        ``chat_link_enabled`` off — exactly that launch state — so the page
        must serve while its own navbar stays silent about it.

        The flag is forced off rather than assumed off: this suite also runs
        against copies of production, where the link has been live since
        2026-08-17, and a fixture assumption is not a state.
        """
        self.websites.write({"chat_link_enabled": False})
        self.registry.clear_cache("templates")
        self.addCleanup(self.registry.clear_cache, "templates")
        response = self._get_index()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("o_cc_chat_menu_link", response.text)

    def test_the_host_website_links_to_its_own_chat(self):
        """With the link opted in, on the portal it is a plain path.

        Same origin, so an absolute URL would be wrong here in exactly the
        deployments where it is hardest to notice: local and staging, where
        the stored domain is not the one the browser is on.
        """
        self.websites.write({"chat_link_enabled": True})
        response = self._get_index()
        self.assertEqual(response.status_code, 200)
        self.assertIn("o_cc_chat_menu_link", response.text)
        self.assertIn('href="/chat"', response.text)
        self.assertIn("Comunidad", response.text)

    def test_a_linked_website_points_at_the_host_by_absolute_url(self):
        """The neighbourhood portals are on their own subdomains.

        A relative ``/chat`` there would 404 on a website that does not serve
        the route, which is the failure this whole field exists to avoid. The
        host is resolved from ``chat_enabled``, never from an id: the URL below
        has to follow the DATA, so the test moves the flag and expects the link
        to move with it.
        """
        # Resolved the way the code resolves it, so the fixture cannot
        # accidentally point at a different website than the one under test.
        host = self.env["website"]._chat_host_website()
        host.domain = "https://canariasconectada.example"
        zone = self._zone_portal()

        self.assertEqual(
            zone._chat_menu_url(),
            "https://canariasconectada.example/chat",
        )

    def test_a_bare_hostname_is_still_turned_into_an_absolute_url(self):
        """Administrators type hostnames into that field, scheme or not.

        Without the scheme the browser reads ``canariasconectada.example/chat``
        as a RELATIVE path and keeps the visitor on the microsite they were
        on -- a broken link that returns 404 instead of looking broken.
        """
        host = self.env["website"]._chat_host_website()
        host.domain = "canariasconectada.example"
        self.assertEqual(
            self._zone_portal()._chat_menu_url(),
            "https://canariasconectada.example/chat",
        )

    def test_a_linked_website_shows_no_entry_when_the_host_has_no_domain(self):
        """An incomplete configuration must cost a tap, not a page.

        The neighbourhood portals are live sites; raising here -- or emitting
        an href of ``False/chat`` -- would turn a blank field on somebody
        else's record into a defect on every page of theirs.
        """
        self.websites.write({"domain": False})
        self.assertFalse(self._zone_portal()._chat_menu_url())

    def test_a_merchant_microsite_gets_no_entry_at_all(self):
        """214 of the 218 sites, and the reason the entry is not a menu record.

        A shop's window is not a public square: a Comunidad link on a
        merchant's storefront pulls a visitor out of the shop they were
        looking at. Neither flag on means the template renders nothing, with
        no menu row to have been forgotten in a data file.
        """
        merchant = self.env["website"].create({"name": "WPC Merchant"})
        self.assertFalse(merchant.chat_enabled)
        self.assertFalse(merchant.chat_link_enabled)
        self.assertFalse(merchant._chat_menu_url())

    # ------------------------------------------------------------------
    # The floating button
    # ------------------------------------------------------------------

    def test_the_floating_button_points_at_support_on_the_site_that_serves_it(self):
        """Support, not the public square: a private conversation.

        The bubble it replaces was Odoo's live chat, which with nobody
        connected only ever answered "no operator is available". This one
        needs nobody connected.
        """
        host = self.env["website"]._chat_host_website()
        self.assertEqual(host._chat_support_url(), "/chat/soporte")

    def test_a_linked_website_gets_an_absolute_support_url(self):
        """The zone portals live on their own subdomains.

        A relative ``/chat/soporte`` there would 404 on a site that does not
        serve the route -- the same reasoning as the menu entry, and the same
        helper, so the two can never drift apart.
        """
        host = self.env["website"]._chat_host_website()
        host.domain = "https://canariasconectada.example"
        self.assertEqual(
            self._zone_portal()._chat_support_url(),
            "https://canariasconectada.example/chat/soporte",
        )

    def test_a_merchant_microsite_gets_no_floating_button(self):
        """214 of the 218 sites. A shop window is not a support desk."""
        merchant = self.env["website"].create({"name": "WPC Merchant FAB"})
        self.assertFalse(merchant._chat_support_url())

    def test_the_button_disappears_with_the_link_opt_in(self):
        """One switch governs the menu entry and the button alike.

        Announcing the chat is a decision, and it has to be reversible from
        the configuration rather than by a deploy.
        """
        host = self.env["website"]._chat_host_website()
        host.chat_link_enabled = False
        self.assertFalse(host._chat_support_url())

    def _zone_portal(self):
        """A website that only LINKS to the chat, like the three zone portals.

        Built here rather than in the fixtures because two of these tests move
        the host's domain around, and a shared record would make them depend on
        each other's order.
        """
        return self.env["website"].create(
            {"name": "WPC Zona", "chat_link_enabled": True}
        )

    # ------------------------------------------------------------------
    # A visitor's message is held, and they are told so
    # ------------------------------------------------------------------

    def test_a_visitor_message_is_held_and_shown_to_its_author(self):
        """The whole conversion moment, end to end.

        Three separate facts, because any one of them alone would let a
        regression through: the route reports the hold (``message_id`` falsy),
        the queue really has the row, and the page tells the AUTHOR in words
        they will understand -- with the invitation to register next to it,
        which is the only reason the hold is worth showing at all.
        """
        result = self._post_over_http(self.channel_general, self.visitor)
        self.assertFalse(
            result["message_id"],
            "a visitor's message is held, not published",
        )
        held = self._held_rows(self.channel_general, self.visitor)
        self.assertEqual(len(held), 1)
        self.assertEqual(held.state, "pending")

        response = self._get_channel(self.channel_general, self.visitor)
        self.assertEqual(response.status_code, 200)
        self.assertIn(UNDER_REVIEW, response.text)
        self.assertIn(HELD_BODY, response.text)
        # The signup CTA, asserted by destination rather than by its
        # translated label so the test survives any database language.
        self.assertIn("/web/signup", response.text)

    def test_a_held_message_is_invisible_to_every_other_visitor(self):
        """The hold has to be a hold, not a badge on a published message.

        Both halves matter and they fail differently. The body leaking would
        publish unmoderated text. The phrase leaking without the body would be
        harmless-looking and still wrong: it would tell a stranger that
        somebody, somewhere, is waiting for review.
        """
        self._post_over_http(self.channel_general, self.visitor)

        response = self._get_channel(self.channel_general, self.other_visitor)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(HELD_BODY, response.text)
        self.assertNotIn(UNDER_REVIEW, response.text)

    def test_an_anonymous_session_is_shown_nobody_elses_held_message(self):
        """The case the shared public partner would have broken.

        A caller with no guest cookie has no identity of its own, and the
        moderation module authors ITS held rows with the one
        ``base.public_partner`` every anonymous request on the platform shares.
        Matching held rows on a partner without excluding that one would show
        every anonymous visitor every other anonymous visitor's message.
        """
        self._post_over_http(self.channel_general, self.visitor)

        response = self._get_channel(self.channel_general, guest=None)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(HELD_BODY, response.text)
        self.assertNotIn(UNDER_REVIEW, response.text)

    def test_the_pending_fragment_route_is_scoped_to_its_caller(self):
        """The fragment route serves markup, so it gets its own test.

        It exists so the invitation to register is written once, but it is a
        public route returning rendered HTML, which is the shape of thing that
        leaks. Asked by a different persona it must render nothing at all --
        not an empty shell with the wording still in it.
        """
        self._post_over_http(self.channel_general, self.visitor)

        mine = self.make_jsonrpc_request(
            "/website_pwa_chat/pending",
            {"channel_id": self.channel_general.id},
            cookies=self._cookies_for(self.visitor),
        )
        theirs = self.make_jsonrpc_request(
            "/website_pwa_chat/pending",
            {"channel_id": self.channel_general.id},
            cookies=self._cookies_for(self.other_visitor),
        )
        self.assertIn(HELD_BODY, mine["html"])
        self.assertIn(UNDER_REVIEW, mine["html"])
        self.assertEqual(theirs["html"].strip(), "")

    # ------------------------------------------------------------------
    # ... and published once a moderator says so
    # ------------------------------------------------------------------

    def test_an_approved_message_is_served_to_everybody(self):
        """Approval is what turns held text into a message on the page.

        Read back by ANOTHER visitor, not by its author: the author's copy
        could come from the pending block and the test would pass with nothing
        published. The author's own page is checked too, for the other half --
        that the "en revisión" card goes away instead of doubling the message.
        """
        self._post_over_http(self.channel_general, self.visitor)
        held = self._held_rows(self.channel_general, self.visitor)
        self._approve(held)
        self.assertEqual(held.state, "approved")

        stranger = self._get_channel(self.channel_general, self.other_visitor)
        self.assertIn(HELD_BODY, stranger.text)

        author = self._get_channel(self.channel_general, self.visitor)
        self.assertIn(HELD_BODY, author.text)
        self.assertNotIn(UNDER_REVIEW, author.text)

    def test_approving_one_message_leaves_the_others_held(self):
        """Two rows from the same persona must not be decided together.

        The page renders every pending row of its caller in one card, which is
        exactly the arrangement in which "the card disappeared" gets mistaken
        for "everything was approved".
        """
        self._post_over_http(self.channel_general, self.visitor, body=HELD_BODY)
        self._post_over_http(self.channel_general, self.visitor, body=OTHER_HELD_BODY)
        held = self._held_rows(self.channel_general, self.visitor)
        self.assertEqual(len(held), 2)
        self._approve(held.filtered(lambda row: HELD_BODY in (row.body or "")))

        response = self._get_channel(self.channel_general, self.visitor)
        self.assertIn(UNDER_REVIEW, response.text)
        self.assertIn(OTHER_HELD_BODY, response.text)

    # ------------------------------------------------------------------
    # A registered user is not moderated
    # ------------------------------------------------------------------

    def test_a_portal_message_is_published_immediately(self):
        """The other side of the invitation: registering has to be worth it.

        ``discuss_channel_zone`` ships the four channels with
        ``moderate_portal`` off, so the promise the page makes to a visitor --
        "create an account and your messages publish at once" -- is a claim
        about configuration that can silently stop being true.
        """
        self.authenticate("dcz_resident", "dcz_resident")
        self._forget_guest_cookie()
        result = self._post_over_http(
            self.channel_general, body="papas arrugadas para todos"
        )
        self.assertTrue(
            result["message_id"],
            "a registered resident's message is published, not held",
        )

        response = self.url_open("/chat/%s" % self.channel_general.id)
        self.assertIn("papas arrugadas para todos", response.text)
        self.assertNotIn(UNDER_REVIEW, response.text)
