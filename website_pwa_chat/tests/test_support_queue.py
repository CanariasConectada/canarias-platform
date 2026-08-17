# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re
from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged

from .common import WebsiteChatMixin

SUPPORT_URL = "/chat/soporte"
IDENTIFY_URL = "/chat/soporte/identificarme"


@tagged("post_install", "-at_install")
class TestSupportQueue(WebsiteChatMixin, HttpCase):
    """The queue the administrators read, and how long it keeps anything.

    Asked for on 2026-08-16: "quiero que puedas agrupar en los chats de discuss
    los soportes para que se vea más ordenado para los administradores […] y
    recuerda el tema de que estos chats también sean temporales", and "que en
    el botón de mensajes podamos pedir que las personas se identifiquen, y si
    se identifica podemos dejar un rato más a las personas en el chat".

    Three promises, and each one is a test here: the state is read off the
    conversation and never typed by hand; a quiet conversation closes and then
    goes away; and telling us your name is what buys the longer window.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_chat_fixtures()
        cls.support_group = cls.env.ref("website_pwa_chat.group_support_agent")
        cls.agent = cls.env["res.users"].create(
            {
                "name": "WPQ Support Agent",
                "login": "wpq_support",
                "email": "wpq_support@example.com",
            }
        )
        # Granted through a ROLE, because `base_user_role` re-derives group_ids
        # inside every write and a group ticked on the user is gone by the next
        # one. See test_support_chat._make_agent for the full story.
        role = cls.env["res.users.role"].create({"name": "WPQ Support"})
        role.write(
            {
                "implied_ids": [
                    (4, cls.env.ref("base.group_user").id),
                    (4, cls.support_group.id),
                ],
                "line_ids": [(0, 0, {"user_id": cls.agent.id})],
            }
        )
        cls.visitor_partner = cls.env["res.partner"].create({"name": "WPQ Visitante"})

    def _open_support(self):
        """Open a conversation the way a visitor does, and return it."""
        self.url_open(SUPPORT_URL)
        return (
            self.env["discuss.channel"]
            .sudo()
            .search([("support_key", "!=", False)], order="id desc", limit=1)
        )

    def _post_as_agent(self, channel):
        return channel.sudo().message_post(
            body="hola", message_type="comment", author_id=self.agent.partner_id.id
        )

    def _post_as_visitor(self, channel):
        """Somebody who is not one of the people who answer.

        A plain partner rather than `base.partner_root`: OdooBot is a system
        user, and `_support_agents` seats the administrators, so posting as it
        would read as an ANSWER and the assertion would pass for the wrong
        reason.
        """
        return channel.sudo().message_post(
            body="y otra cosa",
            message_type="comment",
            author_id=self.visitor_partner.id,
        )

    # ------------------------------------------------------------------
    # The queue
    # ------------------------------------------------------------------
    def test_a_conversation_nobody_answered_reads_as_waiting(self):
        channel = self._open_support()
        self.assertTrue(channel, "opening the page has to open a conversation")
        self.assertEqual(channel.support_state, "waiting")

    def test_an_answer_from_an_agent_moves_it_out_of_the_queue(self):
        channel = self._open_support()
        self._post_as_agent(channel)
        self.assertEqual(channel.support_state, "answered")

    def test_the_state_is_read_off_the_conversation_not_typed(self):
        """A state somebody has to remember to move is wrong by lunchtime."""
        channel = self._open_support()
        self._post_as_agent(channel)
        self.assertEqual(channel.support_state, "answered")
        # The visitor comes back with another question.
        self._post_as_visitor(channel)
        self.assertEqual(channel.support_state, "waiting")

    def test_closing_by_hand_and_reopening_by_writing(self):
        channel = self._open_support()
        channel.action_support_close()
        self.assertEqual(channel.support_state, "closed")
        channel.action_support_reopen()
        self.assertNotEqual(channel.support_state, "closed")

    def test_the_agents_are_seated_but_not_in_their_sidebar(self):
        """Reported 2026-08-17 with a screenshot of Mensajes directos.

        A seat is not an invitation to look. With a button on every page of
        218 shops, every visitor who lands on the support page opens a
        conversation whether or not they type anything, and every one of them
        was sitting pinned in the sidebar of every administrator.

        Seated is still required -- only a member can answer and be notified --
        so what has to be true is both halves at once.
        """
        channel = self._open_support()
        agents = self.env["discuss.channel"]._support_agents()
        self.assertTrue(agents, "the test is worthless without an agent to seat")

        seats = channel.sudo().channel_member_ids.filtered(
            lambda member: member.partner_id in agents.partner_id
        )
        self.assertTrue(seats, "an agent who is not a member cannot answer")
        for seat in seats:
            with self.subTest(agent=seat.partner_id.name):
                self.assertFalse(
                    seat.is_pinned,
                    "an empty conversation must not sit in an agent's sidebar",
                )

    def test_a_conversation_somebody_writes_in_comes_back_on_its_own(self):
        """Unpinned is not hidden: that distinction is the whole design.

        Odoo re-pins a member once the channel has fresh interest, so the
        sidebar ends up showing what has something new and the queue holds the
        rest. If this ever fails, the noise was removed by hiding the signal
        with it.
        """
        channel = self._open_support()
        agents = self.env["discuss.channel"]._support_agents()
        self._post_as_visitor(channel)
        seats = channel.sudo().channel_member_ids.filtered(
            lambda member: member.partner_id in agents.partner_id
        )
        for seat in seats:
            with self.subTest(agent=seat.partner_id.name):
                self.assertTrue(
                    seat.is_pinned,
                    "a visitor who wrote has to reach the people who answer",
                )

    def test_the_visitor_keeps_their_own_conversation_in_sight(self):
        """It is their conversation; only the agents' seats are moved."""
        channel = self._open_support()
        agents = self.env["discuss.channel"]._support_agents()
        theirs = channel.sudo().channel_member_ids.filtered(
            lambda member: member.partner_id not in agents.partner_id
        )
        self.assertTrue(theirs, "the visitor has to be seated in their own thread")
        for seat in theirs:
            self.assertTrue(seat.is_pinned)

    def test_the_queue_is_a_screen_the_agents_can_reach(self):
        menu = self.env.ref(
            "website_pwa_chat.menu_discuss_channel_support", raise_if_not_found=False
        )
        self.assertTrue(menu, "a queue nobody can open is not a queue")
        self.assertIn(self.support_group, menu.group_ids)
        action = self.env.ref("website_pwa_chat.action_discuss_channel_support")
        self.assertIn("search_default_group_state", action.context)

    def test_a_community_channel_is_not_in_the_support_queue(self):
        """The queue is support, not every group chat on the platform."""
        community = (
            self.env["discuss.channel"]
            .sudo()
            .search([("website_chat_published", "=", True)], limit=1)
        )
        self.assertTrue(community)
        self.assertFalse(community.support_state)

    # ------------------------------------------------------------------
    # Temporary
    # ------------------------------------------------------------------
    def _age(self, channel, days):
        channel.sudo().write(
            {"support_last_message_date": fields.Datetime.now() - timedelta(days=days)}
        )

    def test_a_quiet_conversation_closes_itself(self):
        channel = self._open_support()
        self._age(channel, 10)
        self.env["discuss.channel"]._support_gc()
        self.assertTrue(channel.support_closed)

    def test_a_closed_anonymous_conversation_is_deleted_after_a_week(self):
        channel = self._open_support()
        channel.sudo().support_closed = True
        self._age(channel, 10)
        self.env["discuss.channel"]._support_gc()
        self.assertFalse(channel.exists(), "an anonymous week is the promise")

    def test_an_identified_conversation_gets_the_longer_window(self):
        """The whole reason for asking who somebody is."""
        channel = self._open_support()
        channel.sudo().write({"support_closed": True, "support_identified": True})
        self._age(channel, 10)
        self.env["discuss.channel"]._support_gc()
        self.assertTrue(channel.exists(), "ten days is inside the identified window")
        self._age(channel, 40)
        self.env["discuss.channel"]._support_gc()
        self.assertFalse(channel.exists(), "and forty days is outside it")

    def test_a_live_conversation_is_never_deleted(self):
        channel = self._open_support()
        self.env["discuss.channel"]._support_gc()
        self.assertTrue(channel.exists())
        self.assertFalse(channel.support_closed)

    def test_nonsense_in_the_parameters_leaves_the_defaults_alone(self):
        """A window of zero would delete conversations as fast as they open."""
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("website_pwa_chat.support_purge_after_days", "0")
        params.set_param("website_pwa_chat.support_close_after_days", "abc")
        close, purge, identified = self.env["discuss.channel"]._support_retention_days()
        self.assertEqual((close, purge, identified), (3, 7, 30))

    # ------------------------------------------------------------------
    # Identifying yourself
    # ------------------------------------------------------------------
    def test_the_page_asks_an_anonymous_visitor_who_they_are(self):
        page = self.url_open(SUPPORT_URL).text
        self.assertIn("o_cc_chat_identify", page)
        self.assertIn("¿Cómo te llamas?", page)

    def test_the_card_says_what_identifying_buys(self):
        """A form that does not say why is a form nobody fills in."""
        page = self.url_open(SUPPORT_URL).text
        self.assertIn("30 días en vez de 7", page)

    def test_giving_a_name_records_it_and_stops_asking(self):
        page = self.url_open(SUPPORT_URL).text
        self.url_open(
            IDENTIFY_URL,
            data={
                "name": "Marta",
                "email": "marta@example.com",
                "csrf_token": self._csrf_token(page),
            },
        )
        channel = (
            self.env["discuss.channel"]
            .sudo()
            .search([("support_key", "!=", False)], order="id desc", limit=1)
        )
        self.assertTrue(channel.support_identified)
        self.assertEqual(channel.support_visitor_name, "Marta")
        self.assertEqual(channel.support_visitor_email, "marta@example.com")
        self.assertNotIn("o_cc_chat_identify", self.url_open(SUPPORT_URL).text)

    def test_an_empty_name_leaves_the_visitor_anonymous(self):
        """Refusing to say is a perfectly good answer to "who are you"."""
        channel = self._open_support()
        channel._support_identify("   ")
        self.assertFalse(channel.support_identified)

    def _csrf_token(self, page):
        """Scraped from the form itself, which is where a browser gets it."""
        match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page)
        self.assertTrue(match, "the identify form has to carry a csrf token")
        return match.group(1)
