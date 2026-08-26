# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.tools import format_datetime

from odoo.addons.mail.tools.discuss import Store

_logger = logging.getLogger(__name__)

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

# How long a support conversation lives, as system parameters so an
# administrator can widen or narrow them without a deploy. A conversation is
# CLOSED once it has been quiet for a while -- that is what keeps the queue
# readable -- and DELETED a while after that.
#
# The identified window is the whole point of asking a visitor who they are:
# somebody who left a name gets a month, an anonymous cookie gets a week. It
# is also the honest thing to do with a stranger's messages -- keeping them
# longer than the conversation lasted buys nothing and stores more than we
# were given.
PARAM_CLOSE_DAYS = "website_pwa_chat.support_close_after_days"
PARAM_PURGE_DAYS = "website_pwa_chat.support_purge_after_days"
PARAM_PURGE_IDENTIFIED_DAYS = "website_pwa_chat.support_purge_identified_days"
DEFAULT_CLOSE_DAYS = 3
DEFAULT_PURGE_DAYS = 7
DEFAULT_PURGE_IDENTIFIED_DAYS = 30

# A conversation nobody ever wrote in is not a conversation. It used to be
# opened by the page itself, so every crawler and every curious click left
# one behind -- about ninety a day in production, all empty -- and the
# retention windows above, keyed on the last message, kept each of them for
# ten days. The channel is now opened by the FIRST message instead, and this
# window is the safety net for whatever still ends up empty (a post that
# failed after the open, an identify form never followed by a message).
PARAM_EMPTY_PURGE_HOURS = "website_pwa_chat.support_empty_purge_hours"
DEFAULT_EMPTY_PURGE_HOURS = 1

SUPPORT_WAITING = "waiting"
SUPPORT_ANSWERED = "answered"
SUPPORT_CLOSED = "closed"


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

    def _to_store_defaults(self, target):
        """Tell the Discuss client which channels are support conversations.

        A boolean rather than the key itself: the sidebar only needs to know
        WHERE to file the conversation, and the key encodes partner and guest
        ids that no client needs. The frontend patch reads this to move the
        conversation from "Direct messages" into its own collapsible Soporte
        category -- with 218 shops feeding the queue, the DM list was
        drowning.
        """
        return super()._to_store_defaults(target) + [
            Store.Attr("is_support_channel", lambda channel: bool(channel.support_key)),
        ]

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
    def _support_channel_existing(self):
        """The caller's own support conversation if one exists, else empty.

        This is what the page reads. It never creates anything: a page view
        is not participation, and opening a conversation for every visit
        left about ninety empty rows a day behind in production. The
        conversation is opened by ``_support_channel`` on the first message.
        """
        key = self._support_key()
        if not key:
            return self.browse()
        existing = self.sudo().search([("support_key", "=", key)], limit=1)
        if existing:
            # Agents appointed since the conversation opened still belong in it.
            existing._support_seat_agents()
        return existing

    @api.model
    def _support_channel(self):
        """The caller's own support conversation, opening it if this is the first time.

        Called when the visitor actually participates -- their first message,
        or the identify form -- never on a page view.

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

        existing = self._support_channel_existing()
        if existing:
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
        """Put every current agent in the conversation, out of their way.

        Seated, because only a member can answer and be notified. Unpinned,
        because a seat is not an invitation to look: with 218 shops and a
        button on every page, an administrator opening Discuss was met by a
        wall of "Soporte · Visitante" down the whole Mensajes directos list,
        one row per conversation ever opened, most of them empty. Reported
        2026-08-17 with a screenshot of exactly that.

        Odoo re-pins a member the moment the channel has fresh interest
        (`_compute_is_pinned`: `channel.last_interest_dt >= member.unpin_dt`),
        so a conversation somebody actually writes in comes back on its own.
        What stays out of the sidebar is the noise -- an opened page nobody
        typed in -- and the queue under Discusión > Soporte is where the rest
        is read, which is what it was built for.

        The visitor's own seat is never touched: it is their conversation.
        """
        agents = self._support_agents()
        if not agents:
            return
        now = fields.Datetime.now()
        for channel in self.sudo():
            seated = channel.channel_member_ids.partner_id
            missing = agents.partner_id - seated
            if missing:
                channel._add_members(partners=missing, post_joined_message=False)
            channel.channel_member_ids.filtered(
                lambda member, partners=agents.partner_id: member.partner_id in partners
            ).unpin_dt = now

    # ------------------------------------------------------------------
    # Support: what the administrators see, and for how long
    # ------------------------------------------------------------------

    support_state = fields.Selection(
        selection=[
            (SUPPORT_WAITING, "Sin responder"),
            (SUPPORT_ANSWERED, "Respondida"),
            (SUPPORT_CLOSED, "Cerrada"),
        ],
        string="Estado",
        compute="_compute_support_state",
        store=True,
        index=True,
        help="Whether somebody is still waiting for an answer. Computed from "
        "who wrote last, so it cannot fall out of step with the conversation.",
    )
    support_closed = fields.Boolean(
        string="Cerrada a mano o por inactividad",
        copy=False,
        help="Set by an agent or by the nightly sweep. A closed conversation "
        "reopens by itself the moment the visitor writes again.",
    )
    support_last_message_date = fields.Datetime(
        string="Último mensaje",
        compute="_compute_support_state",
        store=True,
        index=True,
    )
    support_identified = fields.Boolean(
        string="Se identificó",
        copy=False,
        help="The visitor told us their name. That is what buys their "
        "conversation the longer retention window.",
    )
    support_visitor_name = fields.Char(string="Quién pregunta", copy=False)
    support_visitor_email = fields.Char(string="Correo de contacto", copy=False)

    @api.depends("message_ids", "message_ids.author_id", "support_closed")
    def _compute_support_state(self):
        """Waiting, answered or closed — read off the conversation itself.

        A separate "state" field an agent has to remember to move is a field
        that is wrong by lunchtime. The only honest signal is who spoke last:
        if it was one of the people who answer, the visitor has an answer; if
        it was the visitor, somebody is waiting.

        The agents are resolved ONCE per call rather than per record: this
        recomputes on every message posted to every support conversation.
        """
        support = self.filtered("support_key")
        (self - support).update(
            {"support_state": False, "support_last_message_date": False}
        )
        if not support:
            return
        agent_partners = self._support_agents().partner_id
        for channel in support:
            # sudo: an agent reading their own queue may not be able to read
            # a guest's message rows, and the state is about the conversation,
            # not about who is looking at it.
            last = (
                self.env["mail.message"]
                .sudo()
                .search(
                    [
                        ("model", "=", "discuss.channel"),
                        ("res_id", "=", channel.id),
                        ("message_type", "!=", "notification"),
                    ],
                    order="id desc",
                    limit=1,
                )
            )
            channel.support_last_message_date = last.date or channel.create_date
            if channel.support_closed:
                channel.support_state = SUPPORT_CLOSED
            elif last and last.author_id and last.author_id in agent_partners:
                channel.support_state = SUPPORT_ANSWERED
            else:
                channel.support_state = SUPPORT_WAITING

    def action_support_close(self):
        """Close by hand. Writing again reopens it, so nothing is lost."""
        self.sudo().write({"support_closed": True})
        return True

    def action_support_reopen(self):
        self.sudo().write({"support_closed": False})
        return True

    @api.model
    def _support_read_param(self, key, default):
        """A positive integer parameter, or its default.

        A zero or negative window would delete conversations as fast as
        they are opened; nonsense is treated as "leave the default alone".
        """
        params = self.env["ir.config_parameter"].sudo()
        try:
            value = int(params.get_param(key) or default)
        except (TypeError, ValueError):
            return default
        return value if value > 0 else default

    @api.model
    def _support_retention_days(self):
        """The three windows, as an administrator has them configured."""
        return (
            self._support_read_param(PARAM_CLOSE_DAYS, DEFAULT_CLOSE_DAYS),
            self._support_read_param(PARAM_PURGE_DAYS, DEFAULT_PURGE_DAYS),
            self._support_read_param(
                PARAM_PURGE_IDENTIFIED_DAYS, DEFAULT_PURGE_IDENTIFIED_DAYS
            ),
        )

    @api.model
    def _support_empty_purge_hours(self):
        """How long an empty conversation is allowed to stay empty."""
        return self._support_read_param(
            PARAM_EMPTY_PURGE_HOURS, DEFAULT_EMPTY_PURGE_HOURS
        )

    def _support_has_messages(self):
        """Whether anybody -- visitor or agent -- ever wrote in here.

        Notifications do not count: "X joined" rows are the platform talking
        to itself, and a conversation made only of those is still empty.
        """
        self.ensure_one()
        return bool(
            self.env["mail.message"]
            .sudo()
            .search_count(
                [
                    ("model", "=", "discuss.channel"),
                    ("res_id", "=", self.id),
                    ("message_type", "!=", "notification"),
                ],
                limit=1,
            )
        )

    def _support_delete(self):
        """Delete these conversations one by one, and report how many went.

        One savepoint each: a single undeletable conversation must not roll
        back the whole sweep.
        """
        deleted = 0
        for channel in self.sudo():
            try:
                with self.env.cr.savepoint():
                    guest = channel._support_guest()
                    channel.unlink()
                    # The visitor's throwaway persona goes with the last
                    # thing it was used for -- but ONLY if that was the
                    # last thing. The same guest may have posted in a
                    # community channel, and deleting them there would
                    # orphan messages other people are reading.
                    if guest and not guest.channel_ids:
                        guest.unlink()
                    deleted += 1
            except Exception:  # noqa: BLE001 - skip it, keep sweeping
                _logger.exception(
                    "website_pwa_chat: could not delete support channel %s",
                    channel.id,
                )
        return deleted

    @api.model
    def _support_gc(self):
        """Cron: close what has gone quiet, delete what has been closed a while,
        and drop what was never written in.

        Support conversations are meant to be temporary. Left alone they would
        become a permanent archive of strangers' messages, and an unreadable
        queue for the people who answer.

        Runs hourly: the two day-sized windows are idempotent, and the empty
        sweep is what wants the shorter cadence.

        Returns ``(closed, deleted, emptied)`` so the log says what it did.
        """
        now = fields.Datetime.now()
        close_days, purge_days, identified_days = self._support_retention_days()

        quiet = self.sudo().search(
            [
                ("support_key", "!=", False),
                ("support_closed", "=", False),
                ("support_last_message_date", "<", now - timedelta(days=close_days)),
            ]
        )
        quiet.write({"support_closed": True})

        # Two windows, one query each, rather than one query and a filter:
        # the identified set is small and the anonymous one is not.
        deleted = 0
        for identified, days in ((False, purge_days), (True, identified_days)):
            stale = self.sudo().search(
                [
                    ("support_key", "!=", False),
                    ("support_closed", "=", True),
                    ("support_identified", "=", identified),
                    (
                        "support_last_message_date",
                        "<",
                        now - timedelta(days=days),
                    ),
                ]
            )
            deleted += stale._support_delete()

        # The empty sweep. Keyed on `create_date` rather than on the last
        # message date, which for a conversation with no messages IS the
        # create date, and it does not wait for the conversation to be closed:
        # there is nothing in it to keep.
        empty_hours = self._support_empty_purge_hours()
        candidates = self.sudo().search(
            [
                ("support_key", "!=", False),
                ("create_date", "<", now - timedelta(hours=empty_hours)),
            ]
        )
        empty = candidates.filtered(lambda channel: not channel._support_has_messages())
        emptied = empty._support_delete()

        _logger.info(
            "website_pwa_chat: support GC closed %s, deleted %s and dropped %s "
            "empty conversations",
            len(quiet),
            deleted,
            emptied,
        )
        return len(quiet), deleted, emptied

    def _support_guest(self):
        """The anonymous persona this conversation belongs to, if it is one.

        Read back out of ``support_key`` rather than off the membership: the
        key is what OPENED the conversation and it never changes, while the
        members list also holds every agent seated since.
        """
        self.ensure_one()
        prefix = SUPPORT_KEY_GUEST % ""
        key = self.support_key or ""
        if not key.startswith(prefix):
            return self.env["mail.guest"]
        raw = key[len(prefix) :]
        if not raw.isdigit():
            return self.env["mail.guest"]
        return self.env["mail.guest"].sudo().browse(int(raw)).exists()

    def _support_identify(self, name, email=None):
        """Record who is asking, and buy them the longer retention window.

        Called from the visitor's own page, so it writes only the three fields
        the form offers and only on the caller's own conversation -- resolved
        by ``_support_channel()`` from the session, never from the form.
        """
        self.ensure_one()
        name = (name or "").strip()
        if not name:
            return False
        values = {
            "support_identified": True,
            "support_visitor_name": name[:120],
            "support_visitor_email": (email or "").strip()[:120] or False,
        }
        self.sudo().write(values)
        # The guest persona carries the name too, so the agent sees it on the
        # message and not only on the row.
        _partner, guest = self.env["res.partner"]._get_current_persona()
        if guest:
            guest.sudo().write({"name": name[:120]})
        return True

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
