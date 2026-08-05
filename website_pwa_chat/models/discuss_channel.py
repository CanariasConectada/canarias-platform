# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.tools import format_datetime

# How many messages the page renders, and how many a single live catch-up
# fetch may return. Deliberately small: this is a phone screen, and the
# "load older messages" button is ROADMAP, not v1.
MESSAGE_LIMIT = 30


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
        return self.search(
            [("id", "=", channel_id), ("website_chat_published", "=", True)]
        )

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
