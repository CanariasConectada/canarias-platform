# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.tools import format_datetime

# How many messages the page renders, and how many a single live catch-up
# fetch may return. Deliberately small: this is a phone screen, and the
# "load older messages" button is ROADMAP, not v1.
MESSAGE_LIMIT = 30

# How a support conversation says whose it is. Two shapes because a visitor
# has two possible identities on this platform and only one of them at a time:
# an account, or the guest cookie the login page hands out.
SUPPORT_KEY_PARTNER = "partner-%s"
SUPPORT_KEY_GUEST = "guest-%s"

# Referenced as a string so this module keeps loading if the group is ever
# renamed or moved; `_support_agents` treats a missing group as "no agents
# from there" rather than as an error on a page a visitor is waiting for.
SUPPORT_GROUP_XMLID = "website_pwa_chat.group_support_agent"


class DiscussChannel(models.Model):
    """The channels the website chat is allowed to offer, and how it reads them.

    Two questions, kept apart on purpose because they have different answers
    and different failure modes:

    - WHICH channels does the chat page know about? ``website_chat_published``,
      an explicit opt-in per channel, seeded on the four community channels.
    - WHO may see each of them? Nothing in this module. It is
      ``ir_rule_discuss_channel_all`` (``mail/security/mail_security.xml:3-28``)
      applied to a ``search()`` run as the visitor.

    Merging the two -- listing every ``channel_type == "channel"`` the visitor
    can read -- was the obvious shortcut and it is wrong in a way that only
    shows up in production. Core creates channels with ``group_public_id``
    explicitly None on ``/chat/<create_token>``
    (``mail/controllers/discuss/public_page.py:75-83``), ``mail`` seeds
    ``channel_all_employees``, and any user with write access can make more.
    Every one of those would have appeared on a public page nobody meant to
    publish them on. The opt-in flag makes publication a decision; the record
    rule keeps it from ever becoming a permission.
    """

    _inherit = "discuss.channel"

    website_chat_published = fields.Boolean(
        string="En el chat de la web",
        default=False,
        index=True,
        help="When enabled, this channel is offered on the community chat "
        "page of the website. It does NOT grant access to anybody: who can "
        "read and post is still decided by the channel's own group.",
    )

    # ------------------------------------------------------------------
    # The list
    # ------------------------------------------------------------------

    @api.model
    def _website_chat_channels(self):
        """The published channels THIS visitor may actually open.

        No ``sudo()``, and that absence is the security property. The search
        runs with the caller's own environment, so
        ``ir_rule_discuss_channel_all`` rewrites it into "published AND
        (group_public_id is False OR group_public_id in my groups)". An
        anonymous session runs as ``base.public_user``, whose only group is
        ``base.group_public``, which does not imply
        ``discuss_channel_zone.group_zone_channel_member`` -- so the three
        neighbourhood channels are filtered out of the result by the database,
        not by this module.

        That matters beyond tidiness: a list built any other way could offer a
        visitor a link that 404s, and a link that 404s is how a product teaches
        people that it is broken.
        """
        return self.search([("website_chat_published", "=", True)], order="id")

    @api.model
    def _website_chat_channel(self, channel_id):
        """One published channel, or an empty recordset.

        Same search, same rule, one extra leaf: a channel the visitor may not
        read simply does not come back, and the caller turns that into a 404.
        Exactly what ``/discuss/channel/messages`` does
        (``mail/controllers/discuss/channel.py:90-92``), so the page and the
        JSON routes it calls cannot disagree about what exists.
        """
        published = self.search(
            [("id", "=", channel_id), ("website_chat_published", "=", True)]
        )
        if published:
            return published
        # A support conversation is never published, so the search above can
        # never find one — and the live catch-up and held-message routes both
        # come back through here. The fallback is narrow on purpose: the key
        # comes from the session, so the only support conversation this can
        # ever return is the caller's own, and the search still runs without
        # sudo so `is_member` is what finally answers.
        key = self._support_key()
        if not key:
            return self.browse()
        return self.search([("id", "=", channel_id), ("support_key", "=", key)])

    # ------------------------------------------------------------------
    # The messages
    # ------------------------------------------------------------------

    def _website_chat_messages(self, after=None, limit=MESSAGE_LIMIT):
        """Published messages of this channel, oldest first.

        Goes through ``mail.message._message_fetch``, the same entry point the
        public route uses (``mail/controllers/discuss/channel.py:93``), so the
        access decision is core's and not a domain reinvented here.

        Sorted ascending because that is reading order. ``_message_fetch``
        answers ``id DESC`` for the initial page and ``id ASC`` for an
        ``after`` catch-up (``mail/models/mail_message.py:991``), and a list
        that flips direction depending on how it was asked for is a bug
        waiting for the first live message.
        """
        self.ensure_one()
        fetched = self.env["mail.message"]._message_fetch(
            None, thread=self, after=after, limit=limit
        )
        return fetched["messages"].sorted("id")

    def _website_chat_message_values(self, messages):
        """Flat, JSON-safe dicts: id, author, body, date, mine.

        WHY NOT ``Store``. Core serves messages as a normalised graph
        (``mail.message`` rows referencing ``res.partner`` / ``mail.guest``
        rows by id) meant to be rehydrated by the Discuss OWL store. That store
        lives in ``web.assets_backend`` and only reaches the public site
        through ``im_livechat``'s embed bundle, which this module exists not to
        require. Re-implementing its deserialiser in a hundred lines of
        frontend JS would be strictly worse than emitting the four fields the
        page actually renders -- and it would break on the next refactor of a
        format that is explicitly internal.

        ``sudo()`` on the author is core's own choice, not a shortcut: a public
        session cannot read ``res.partner``, so ``Store`` reads both author
        fields with ``sudo=True`` and says so
        (``mail/models/mail_message.py:1105-1109``). The name of whoever wrote
        a message in a channel the reader is already allowed to read is public
        by construction. Nothing else about the author is exposed.
        """
        values = []
        for message in messages:
            # sudo: author identity of a message the caller may already read;
            # same read, same justification as mail.message._to_store.
            message_sudo = message.sudo()
            author = (
                message_sudo.author_id.name
                or message_sudo.author_guest_id.name
                or _("Anónimo")
            )
            values.append(
                {
                    "id": message.id,
                    "author": author,
                    # Sanitised on write by the field itself; this is the exact
                    # markup core serves on the public route.
                    "body": message_sudo.body or "",
                    "date": format_datetime(self.env, message_sudo.date),
                    "mine": message.is_current_user_or_guest_author,
                }
            )
        return values

    # ------------------------------------------------------------------
    # The messages that are NOT published yet
    # ------------------------------------------------------------------

    def _website_chat_pending(self):
        """The held messages of the CURRENT persona on this channel. Only theirs.

        THE leak this method is shaped to avoid: a public session with no guest
        cookie has no identity of its own, and
        ``discuss_channel_moderation`` authors its held rows with the ONE
        ``base.public_partner`` shared by every anonymous request on the
        platform (``_moderation_persona``). Matching held rows on that partner
        would show every anonymous visitor every other anonymous visitor's
        message awaiting review -- the precise opposite of what a moderation
        queue is for.

        ``res.partner._get_current_persona()``
        (``mail/models/res_partner.py:341-344``) is what makes the guard
        structural rather than a forgotten ``if``: for a public session it
        returns an EMPTY partner and the guest from the context, never the
        public partner. So the partner branch is unreachable from an anonymous
        request, and a cookie-less visitor is shown nothing.

        ``sudo()`` is unavoidable and bounded: the ACL of
        ``discuss.channel.pending.message`` grants read to moderators only
        (``discuss_channel_moderation/security/ir.model.access.csv``), by
        design -- the queue is not public data. The domain below is the entire
        access policy of this read, so it names the persona explicitly instead
        of trusting a filter applied later.
        """
        self.ensure_one()
        partner, guest = self.env["res.partner"]._get_current_persona()
        if guest:
            author_domain = [("guest_id", "=", guest.id)]
        elif partner:
            author_domain = [("partner_id", "=", partner.id)]
        else:
            return self.env["discuss.channel.pending.message"].browse()
        # sudo: reading the caller's OWN held rows, pinned to their persona by
        # the domain; the model is closed to everybody but moderators.
        return (
            self.env["discuss.channel.pending.message"]
            .sudo()
            .search(
                [("channel_id", "=", self.id), ("state", "=", "pending")]
                + author_domain,
                order="id",
            )
        )

    # ------------------------------------------------------------------
    # Support: one private conversation per visitor
    # ------------------------------------------------------------------

    support_key = fields.Char(
        string="Conversación de soporte de",
        index=True,
        copy=False,
        help="Identifies whose support conversation this is. Set by the "
        "platform, never by hand.",
    )

    @api.model
    def _support_key(self):
        """Who is asking, as a stable string, or False when nobody is.

        A logged-in account wins over a guest cookie: somebody who signed in
        halfway through a conversation should keep writing as themselves, and
        the account is the identity that survives a new phone.

        Returns False for the anonymous public user, and that is deliberate.
        ``base.public_partner`` is ONE record shared by every anonymous hit on
        the platform, so a conversation keyed on it would be a single room
        that every stranger on the internet walks into and reads. The caller
        turns that False into "get an identity first", which on this platform
        means the guest door the login page already offers.
        """
        user = self.env.user
        if not user._is_public():
            return SUPPORT_KEY_PARTNER % user.partner_id.id
        guest = self.env["mail.guest"]._get_guest_from_context()
        if guest:
            return SUPPORT_KEY_GUEST % guest.id
        return False

    @api.model
    def _support_agents(self):
        """The users who answer. Never empty if the database has an admin.

        Administrators are included explicitly even though
        ``ir_rule_discuss_channel_group_system`` already lets them read every
        channel: reading is not the same as being seated. Only a member gets
        the conversation in their Discuss sidebar, and a support queue nobody
        is shown is a support queue nobody answers.
        """
        # sudo from the FIRST recordset, not only on each group. A union takes
        # the environment of its left operand, so starting from the visitor's
        # env would quietly drag every agent back into it — and the caller
        # here is usually `base.public_user`, who cannot read another user's
        # row. That is not theoretical: it shipped, and the queue came out
        # seated with the administrators and without the one person actually
        # appointed to answer. Who staffs support is the platform's answer to
        # give, never the visitor's to read.
        agents = self.env["res.users"].sudo()
        for xmlid in (SUPPORT_GROUP_XMLID, "base.group_system"):
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                agents |= group.sudo().all_user_ids
        # The technical accounts are seats nobody sits in.
        return agents.filtered(lambda user: user.active and not user._is_public())

    @api.model
    def _support_channel(self):
        """The caller's own support conversation, opening it if this is the first time.

        ``channel_type`` is ``group`` and that single value is the privacy of
        this feature. ``ir_rule_discuss_channel_all`` has two branches: for
        ``channel_type == "channel"`` it asks about ``group_public_id``, which
        is a door held open for a whole group of people; for everything else
        it asks ``is_member``. Only the second branch describes "this visitor
        and the people who answer them", so anything of type ``channel`` --
        including a private-looking one with no group -- would have been
        readable by every logged-in visitor on the platform.

        sudo on the create: a guest cannot create a channel, and a portal user
        cannot seat anybody but themselves. The identity being seated is not
        taken from the caller's input at any point -- it is derived from the
        session by ``_support_key`` -- so there is nothing here for a caller
        to aim somewhere else.
        """
        key = self._support_key()
        if not key:
            return self.browse()

        existing = self.sudo().search([("support_key", "=", key)], limit=1)
        if existing:
            # Agents appointed since the conversation opened still belong in it.
            existing._support_seat_agents()
            return existing

        partner, guest = self.env["res.partner"]._get_current_persona()
        channel = (
            self.sudo()
            .with_context(
                # Core posts "X joined the channel" for every seat taken. On a
                # support thread that is the first thing the visitor reads,
                # and it is a list of strangers' names before they have said
                # a word. The conversation opens empty instead.
                mail_create_nosubscribe=True,
            )
            .create(
                {
                    "name": _(
                        "Soporte · %s", (partner.name or guest.name or _("Visitante"))
                    ),
                    "channel_type": "group",
                    "support_key": key,
                    # Never on the public list: that flag is what `/chat` reads.
                    "website_chat_published": False,
                }
            )
        )
        channel._add_members(
            partners=partner or None,
            guests=guest or None,
            post_joined_message=False,
        )
        channel._support_seat_agents()
        return channel

    def _support_seat_agents(self):
        """Put every current agent in the conversation, without disturbing the rest."""
        agents = self._support_agents()
        if not agents:
            return
        for channel in self.sudo():
            seated = channel.channel_member_ids.partner_id
            missing = agents.partner_id - seated
            if missing:
                channel._add_members(partners=missing, post_joined_message=False)

    @api.model
    def _support_sync_agents(self):
        """Cron: keep every open support conversation seated with today's agents.

        Granting somebody the support group is a two-second action in Settings
        and it has to be enough. Without this, a new agent would only ever see
        conversations opened after their appointment, and the ones already
        waiting for an answer would stay invisible to the person hired to
        answer them.
        """
        channels = self.sudo().search([("support_key", "!=", False)])
        channels._support_seat_agents()
        return len(channels)
