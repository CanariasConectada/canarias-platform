# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.addons.discuss_channel_zone.tests.common import ZoneChannelMixin

# Bodies used by the suite. Distinctive on purpose: every visibility assertion
# below is "is this string in the HTML", so a body that could plausibly occur
# in a theme, a menu or another test's fixture would make the assertion lie in
# whichever direction is most comfortable.
HELD_BODY = "sardinas del muelle a las ocho"
OTHER_HELD_BODY = "gofio escaldado para dos"

# The one phrase the page shows the author of a held message, and nobody else.
# Asserted as a substring rather than through a marker class because it is the
# PRODUCT promise, not a DOM detail: if the wording ever stops saying this, the
# visitor stops being told what happened to their message.
# The held-message card's own class, closing quote included so the
# always-present o_cc_chat_pending_zone container never matches. Asserting
# the translated phrase broke on CI, whose fresh DB renders en_US.
UNDER_REVIEW = 'o_cc_chat_pending"'


class WebsiteChatMixin(ZoneChannelMixin):
    """The community scenario of ``discuss_channel_zone``, served over HTTP.

    Everything about WHO may see WHAT already has a suite in that module; this
    one is about what the website page does with the answer, so it inherits the
    fixtures rather than rebuilding a second, subtly different community.
    """

    @classmethod
    def _setup_chat_fixtures(cls):
        cls._setup_zone_fixtures()

        # EVERY website, not "the default one". This database runs 218 sites
        # and `HttpCase` reaches whichever one the base URL resolves to at
        # runtime; pinning `website.default_website` would make the suite pass
        # or fail on a detail that has nothing to do with the chat. Enabling
        # the flags everywhere removes that variable, and the test that proves
        # the switch really gates the route turns them all back off.
        cls.websites = cls.env["website"].search([])
        cls.websites.write(
            {"chat_enabled": True, "pwa_enabled": True, "chat_link_enabled": True}
        )

        cls.moderator = cls.env["res.users"].create(
            {
                "name": "WPC Moderator",
                "login": "wpc_moderator",
                "password": "wpc_moderator",
                "email": "wpc_moderator@example.com",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref(
                                "discuss_channel_moderation.group_moderation_manager"
                            ).id,
                        ],
                    )
                ],
            }
        )

        cls.visitor, cls.other_visitor = cls.env["mail.guest"].create(
            [{"name": "WPC Visitante"}, {"name": "WPC Otro Visitante"}]
        )

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def _forget_guest_cookie(self):
        """Leave the HTTP session with NO visitor cookie.

        ``self.opener`` is persistent, and the channel page CREATES a guest for
        any anonymous caller that arrives without one -- so without this,
        "anonymous" would quietly mean "the guest the previous request was
        given", and the least identified case, the one the security property is
        about, would never be exercised.
        """
        self.opener.cookies.pop(self.env["mail.guest"]._cookie_name, None)

    def _cookies_for(self, guest):
        """Cookies of a persona, clearing the session when there is none.

        Format ``<id>|<access_token>``
        (``mail/models/discuss/mail_guest.py:150-157``). ``access_token`` is
        behind ``base.group_system``, hence the sudo.
        """
        if not guest:
            self._forget_guest_cookie()
            return None
        return {
            self.env["mail.guest"]._cookie_name: "%s|%s"
            % (guest.id, guest.sudo().access_token)
        }

    # ------------------------------------------------------------------
    # The pages
    # ------------------------------------------------------------------

    def _get_index(self, guest=None):
        return self.url_open("/chat", cookies=self._cookies_for(guest))

    def _get_channel(self, channel, guest=None):
        return self.url_open("/chat/%s" % channel.id, cookies=self._cookies_for(guest))

    def _channel_link(self, channel):
        """The exact href the index renders for a channel.

        Compared with the closing quote included so that ``/chat/1`` cannot
        match inside ``/chat/12`` -- the ids of four records seeded one after
        another are exactly the range where that silently happens.
        """
        return 'href="/chat/%s"' % channel.id

    # ------------------------------------------------------------------
    # Posting and moderating
    # ------------------------------------------------------------------

    def _post_over_http(self, channel, guest=None, body=HELD_BODY):
        """Post through the public route the page really uses.

        Not through ``message_post``: the whole contract this page depends on
        -- ``message_id`` coming back falsy when the message was held -- is a
        property of ``/mail/message/post``, and it is only observable from
        outside.
        """
        return self.make_jsonrpc_request(
            "/mail/message/post",
            {
                "thread_model": "discuss.channel",
                "thread_id": channel.id,
                "post_data": {
                    "body": body,
                    "message_type": "comment",
                    "subtype_xmlid": "mail.mt_comment",
                },
            },
            cookies=self._cookies_for(guest),
        )

    def _held_rows(self, channel, guest):
        return (
            self.env["discuss.channel.pending.message"]
            .sudo()
            .search([("channel_id", "=", channel.id), ("guest_id", "=", guest.id)])
        )

    def _approve(self, pending):
        """Approve as a real moderator, never as superuser.

        ``_check_moderator`` has no ``sudo()`` escape hatch on purpose
        (``discuss_channel_moderation``), so approving from the test
        environment would prove nothing about the path a moderator takes.
        """
        return pending.with_user(self.moderator).action_approve()
