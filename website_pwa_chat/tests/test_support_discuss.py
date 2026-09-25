# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import importlib.util
from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import HttpCase
from odoo.tests import common as test_common
from odoo.tests import tagged
from odoo.tests.common import JsonRpcException
from odoo.tools.misc import file_path

from ..models.discuss_channel import SUPPORT_IDENTITY_MAX, SUPPORT_NAME_MAX
from .common import WebsiteChatMixin

REQUEST_URL = "/website_pwa_chat/support/request"


class SupportDiscussMixin(WebsiteChatMixin):
    @classmethod
    def _setup_support_discuss(cls):
        cls._setup_chat_fixtures()
        cls.support_group = cls.env.ref("website_pwa_chat.group_support_agent")
        cls.agent = cls._make_user(
            "wpc_sd_agent", "WPC SD Agent", extra_groups=[cls.support_group]
        )
        cls.merchant = cls._make_user("wpc_sd_merchant", "Ferretería Las Canteras")

    @classmethod
    def _make_user(cls, login, name, extra_groups=(), **values):
        groups = [(4, cls.env.ref("base.group_user").id)]
        groups += [(4, group.id) for group in extra_groups]
        return cls.env["res.users"].create(
            {
                "name": name,
                "login": login,
                # HttpCase.start_tour(login=...) signs in with login as password.
                "password": login,
                "email": "%s@example.com" % login,
                "group_ids": groups,
                **values,
            }
        )

    def _support_of(self, user):
        return (
            self.env["discuss.channel"]
            .sudo()
            .search([("support_key", "=", "partner-%s" % user.partner_id.id)])
        )


@tagged("post_install", "-at_install")
class TestSupportFromDiscuss(SupportDiscussMixin, HttpCase):
    """Requirement 10: asking for support from the backend Discuss app."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_support_discuss()

    def test_a_merchant_opens_one_conversation_and_reopens_it(self):
        self.authenticate(self.merchant.login, self.merchant.login)

        first = self.make_jsonrpc_request(REQUEST_URL, {})
        channel = self.env["discuss.channel"].sudo().browse(first["channel_id"])
        self.assertEqual(channel, self._support_of(self.merchant))
        self.assertEqual(channel.channel_type, "group")
        self.assertIn("Ferretería Las Canteras", channel.name)
        self.assertIn(self.merchant.partner_id, channel.channel_member_ids.partner_id)

        channel.action_support_close()
        second = self.make_jsonrpc_request(REQUEST_URL, {})
        self.assertEqual(second["channel_id"], channel.id, "asked twice, one line")
        self.assertEqual(len(self._support_of(self.merchant)), 1)
        self.assertFalse(channel.support_closed, "asking again reopens it")

    def test_the_same_agents_are_seated_as_for_the_website(self):
        channel = (
            self.env["discuss.channel"]
            .with_user(self.merchant)
            ._support_request_from_discuss()
        )
        seated = channel.sudo().channel_member_ids.partner_id
        self.assertIn(self.agent.partner_id, seated)
        self.assertIn(self.env.ref("base.user_admin").partner_id, seated)

    def test_the_session_offers_the_entry_to_non_agents_only(self):
        self.authenticate(self.merchant.login, self.merchant.login)
        info = self.make_jsonrpc_request("/web/session/get_session_info", {})
        self.assertTrue(info.get("website_pwa_chat_can_request_support"))

        self.authenticate(self.agent.login, self.agent.login)
        info = self.make_jsonrpc_request("/web/session/get_session_info", {})
        self.assertFalse(info.get("website_pwa_chat_can_request_support"))

    def test_an_agent_is_refused_by_the_route(self):
        self.authenticate(self.agent.login, self.agent.login)
        with self.assertRaises(JsonRpcException):
            self.make_jsonrpc_request(REQUEST_URL, {})
        self.assertFalse(self._support_of(self.agent))

    def test_the_sidebar_entry_opens_the_conversation(self):
        # No screencast for this one. Discuss keeps repainting (avatars,
        # typing, the bus) right up to the moment the harness closes Chrome,
        # and with screencasts on (the lab's config) a frame acknowledged on
        # the closing socket fails the test with a BrokenPipeError AFTER the
        # tour has already succeeded. Nothing here is about the recording.
        with patch.object(
            test_common, "Screencaster", lambda *args: test_common.NoScreencast()
        ):
            self.start_tour(
                "/odoo/discuss",
                "website_pwa_chat_support_request_discuss",
                login=self.merchant.login,
            )
        self.assertEqual(len(self._support_of(self.merchant)), 1)

    def test_an_administrator_is_an_agent_too(self):
        admin = self.env.ref("base.user_admin")
        Channel = self.env["discuss.channel"].with_user(admin)
        self.assertFalse(Channel._support_can_request_from_discuss())
        with self.assertRaises(AccessError):
            Channel._support_request_from_discuss()

    def test_an_anonymous_caller_gets_no_conversation(self):
        self.authenticate(None, None)
        before = (
            self.env["discuss.channel"]
            .sudo()
            .search_count([("support_key", "!=", False)])
        )
        with self.assertRaises(JsonRpcException):
            self.make_jsonrpc_request(REQUEST_URL, {})
        after = (
            self.env["discuss.channel"]
            .sudo()
            .search_count([("support_key", "!=", False)])
        )
        self.assertEqual(before, after)


@tagged("post_install", "-at_install")
class TestSupportFromDiscussCommunityGuest(SupportDiscussMixin, HttpCase):
    """The walk-in community guest is asked their name before it opens."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_support_discuss()
        if "is_community_guest" not in cls.env["res.users"]._fields:
            cls.walk_in = None
            return
        cls.walk_in = cls._make_user(
            "wpc_sd_walkin2", "Invitado 7c1e0b", is_community_guest=True
        )

    def setUp(self):
        super().setUp()
        if not self.walk_in:
            self.skipTest("discuss_community is not installed")

    def _request(self, **params):
        self.authenticate(self.walk_in.login, self.walk_in.login)
        return self.make_jsonrpc_request(REQUEST_URL, params)

    def test_the_session_asks_a_guest_for_a_name_and_nobody_else(self):
        self.authenticate(self.walk_in.login, self.walk_in.login)
        info = self.make_jsonrpc_request("/web/session/get_session_info", {})
        self.assertTrue(info.get("website_pwa_chat_support_asks_name"))

        self.authenticate(self.merchant.login, self.merchant.login)
        info = self.make_jsonrpc_request("/web/session/get_session_info", {})
        self.assertFalse(info.get("website_pwa_chat_support_asks_name"))

    def test_the_typed_name_identifies_and_renames(self):
        result = self._request(name="  Carmen la del kiosco ", email="c@example.com")

        channel = self.env["discuss.channel"].sudo().browse(result["channel_id"])
        self.assertEqual(channel, self._support_of(self.walk_in))
        self.assertTrue(channel.support_identified)
        self.assertEqual(channel.support_visitor_name, "Carmen la del kiosco")
        self.assertEqual(channel.support_visitor_email, "c@example.com")
        self.assertIn("Carmen la del kiosco", channel.name)
        self.assertNotIn("Invitado", channel.name)

    def test_an_empty_name_is_refused_and_opens_nothing(self):
        for name in (None, "", "   "):
            with self.subTest(name=name), self.assertRaises(JsonRpcException):
                self._request(name=name)
        self.assertFalse(self._support_of(self.walk_in))

    def test_a_long_name_is_capped(self):
        result = self._request(name="Carmen " * 50)
        channel = self.env["discuss.channel"].sudo().browse(result["channel_id"])
        self.assertLessEqual(len(channel.support_visitor_name), SUPPORT_IDENTITY_MAX)
        self.assertLessEqual(len(channel.name), SUPPORT_NAME_MAX)

    def test_an_identified_guest_may_come_back_without_retyping(self):
        first = self._request(name="Carmen la del kiosco")
        again = self._request()
        self.assertEqual(first["channel_id"], again["channel_id"])
        channel = self.env["discuss.channel"].sudo().browse(again["channel_id"])
        self.assertIn("Carmen la del kiosco", channel.name)

    def test_a_non_guest_is_named_after_the_account_whatever_it_sends(self):
        self.authenticate(self.merchant.login, self.merchant.login)
        result = self.make_jsonrpc_request(REQUEST_URL, {"name": "Otro nombre"})
        channel = self.env["discuss.channel"].sudo().browse(result["channel_id"])
        self.assertIn("Ferretería Las Canteras", channel.name)
        self.assertFalse(channel.support_visitor_name)

    def test_the_dialog_asks_and_the_conversation_carries_the_name(self):
        with patch.object(
            test_common, "Screencaster", lambda *args: test_common.NoScreencast()
        ):
            self.start_tour(
                "/odoo/discuss",
                "website_pwa_chat_support_request_discuss_guest",
                login=self.walk_in.login,
            )
        channel = self._support_of(self.walk_in)
        self.assertEqual(channel.support_visitor_name, "Carmen la del kiosco")


@tagged("post_install", "-at_install")
class TestSupportChannelName(SupportDiscussMixin, HttpCase):
    """Requirement 11: the agent reads WHO is asking on the conversation."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_support_discuss()

    def _identify(self, name, cookies=None):
        page = self.url_open("/chat/soporte", cookies=cookies)
        csrf = page.text.split('name="csrf_token"')[1].split('value="')[1]
        csrf = csrf.split('"')[0]
        return self.url_open(
            "/chat/soporte/identificarme",
            data={"name": name, "csrf_token": csrf},
            allow_redirects=False,
        )

    def test_a_visitor_who_gives_a_name_renames_the_conversation(self):
        self._forget_guest_cookie()
        channel = self._open_support()
        self.assertNotIn("Vecina del Puerto", channel.name)

        self._identify("Vecina del Puerto")

        channel.invalidate_recordset(["name"])
        self.assertIn("Vecina del Puerto", channel.name)
        self.assertEqual(channel.support_visitor_name, "Vecina del Puerto")

    def test_a_signed_in_user_is_named_after_their_account(self):
        channel = (
            self.env["discuss.channel"]
            .with_user(self.merchant)
            ._support_request_from_discuss()
        )
        self.assertIn(self.merchant.partner_id.name, channel.name)

    def test_a_community_guest_is_named_after_what_they_typed(self):
        if "is_community_guest" not in self.env["res.users"]._fields:
            self.skipTest("discuss_community is not installed")
        walk_in = self._make_user(
            "wpc_sd_walkin", "Invitado 3f9a2c", is_community_guest=True
        )
        self.authenticate(walk_in.login, walk_in.login)

        page = self.url_open("/chat/soporte")
        self.assertIn(
            "o_cc_chat_identify",
            page.text,
            "an account named 'Invitado …' is asked who is behind it",
        )
        self._identify("Carmen la del kiosco")

        channel = self._support_of(walk_in)
        self.assertEqual(len(channel), 1)
        self.assertIn("Carmen la del kiosco", channel.name)
        self.assertNotIn("Invitado", channel.name)

    def test_a_regular_account_is_not_asked_for_a_name(self):
        self.authenticate(self.merchant.login, self.merchant.login)
        page = self.url_open("/chat/soporte")
        self.assertNotIn('class="o_cc_chat_identify', page.text)

    def test_a_long_name_is_cut_to_what_the_sidebar_can_show(self):
        channel = (
            self.env["discuss.channel"]
            .with_user(self.merchant)
            ._support_request_from_discuss()
        )
        channel._support_identify("Nombre " * 40)
        self.assertLessEqual(len(channel.name), SUPPORT_NAME_MAX)
        self.assertTrue(channel.name.endswith("…"))

    def test_the_rename_writes_a_plain_name_when_it_is_not_translatable(self):
        if self.env["discuss.channel"]._fields["name"].translate:
            self.skipTest("discuss.channel.name is translatable here")
        channel = (
            self.env["discuss.channel"]
            .with_user(self.merchant)
            ._support_request_from_discuss()
        )
        channel.name = "Soporte · Visitante"
        with patch.object(
            type(self.env["discuss.channel"]), "update_field_translations"
        ) as update:
            channel._support_refresh_name()
        update.assert_not_called()
        self.assertEqual(
            channel.name, channel._support_channel_name("Ferretería Las Canteras")
        )

    def test_the_rename_writes_every_language_when_it_is_translatable(self):
        """The other PR makes the name translatable; the rename must follow.

        Simulated by flagging the field, with the translation writer mocked:
        the column underneath is still varchar, so only the choice of writer
        is asserted here, not the storage.
        """
        channel = (
            self.env["discuss.channel"]
            .with_user(self.merchant)
            ._support_request_from_discuss()
        )
        field = self.env["discuss.channel"]._fields["name"]
        installed = [code for code, _label in self.env["res.lang"].get_installed()]
        with patch.object(field, "translate", True), patch.object(
            type(self.env["discuss.channel"]), "update_field_translations"
        ) as update:
            channel._support_refresh_name()
        update.assert_called_once()
        fname, values = update.call_args.args
        self.assertEqual(fname, "name")
        self.assertEqual(set(values), set(installed))
        self.assertEqual(
            set(values.values()),
            {channel._support_channel_name("Ferretería Las Canteras")},
        )

    def test_the_migration_backfills_the_existing_conversations(self):
        self._forget_guest_cookie()
        by_guest = self._open_support()
        by_account = (
            self.env["discuss.channel"]
            .with_user(self.merchant)
            ._support_request_from_discuss()
        )
        # What 19.0.6.3.1 left behind: the name set at open time, never again.
        by_guest.write(
            {"name": "Soporte · Visitante", "support_visitor_name": "Don Tomás"}
        )
        by_account.write({"name": "Soporte · Visitante"})

        path = file_path("website_pwa_chat/migrations/19.0.6.4.0/post-migration.py")
        spec = importlib.util.spec_from_file_location("wpc_backfill", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        migration.migrate(self.env.cr, "19.0.6.3.1")
        (by_guest | by_account).invalidate_recordset(["name"])

        self.assertEqual(by_guest.name, "Soporte · Don Tomás")
        self.assertEqual(by_account.name, "Soporte · Ferretería Las Canteras")


@tagged("post_install", "-at_install")
class TestSupportWindowSizeDesktop(SupportDiscussMixin, HttpCase):
    """Requirement 12: the floating window is tall enough to read."""

    browser_size = "1366x900"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_chat_fixtures()

    def _plain_page(self):
        self.env["website.page"].create(
            {
                "name": "WPC Size Page",
                "url": "/wpc-size-page",
                "is_published": True,
                "type": "qweb",
                "key": "website_pwa_chat.wpc_size_page",
                "arch": '<t t-call="website.layout">'
                '<div id="wrap"><p>wpc size page</p></div></t>',
            }
        )
        self.registry.clear_cache("templates")
        self.addCleanup(self.registry.clear_cache, "templates")
        return "/wpc-size-page"

    def test_the_window_is_sized_to_be_read(self):
        # The site's own default language, so no language redirect happens:
        # on a multi-language database the browser's Accept-Language sends
        # every URL through /xx/, and website_pwa's service-worker
        # registration then fails with "script resource is behind a
        # redirect", which the browser test counts as a failure of its own.
        website = self.env["website"].get_current_website()
        self.start_tour(
            self._plain_page(),
            "website_pwa_chat_support_window_size",
            cookies={"frontend_lang": website.default_lang_id.code},
        )


@tagged("post_install", "-at_install")
class TestSupportWindowSizePhone(TestSupportWindowSizeDesktop):
    browser_size = "390x844"
    touch_enabled = True
