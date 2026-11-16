# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models
from odoo.fields import Domain

# How many mention suggestions a community guest may ask for in one call.
# Core's own default; the cap only stops a client from asking for thousands.
GUEST_MENTION_LIMIT = 8

# Context key carrying the partners a guest may be offered as mentions.
# It can only NARROW a search (it is AND-ed), so a client sending it gains
# nothing; the guest override always overwrites it.
GUEST_MENTION_CTX = "community_guest_mention_partner_ids"


class ResPartner(models.Model):
    """Keep channel rosters out of a community member's @-mention suggestions.

    Core's ``get_mention_suggestions_from_channel`` filters partners with
    ``("channel_ids", "in", channel)``, a many2many condition compiled
    straight to SQL on ``discuss_channel_member`` -- the member record rules
    never see it. A guest asking with an empty search and a large limit on
    "Canarias Conectada" would get the whole roster (names, avatars, emails).

    What a guest may mention instead:

    * in a ``channel``: the people who POSTED in it (they are already on
      screen, with name and avatar, in the messages the guest can read) and
      the guest itself. Silent members stay invisible, exactly as the member
      read rule keeps them;
    * in a chat or group: its members, who are the conversation.
    """

    _inherit = "res.partner"

    @api.readonly
    @api.model
    def get_mention_suggestions_from_channel(self, channel_id, search, limit=8):
        if not self.env.user.is_community_member:
            return super().get_mention_suggestions_from_channel(
                channel_id, search, limit=limit
            )
        channel = self.env["discuss.channel"].search([("id", "=", channel_id)])
        if not channel:
            return []
        allowed = self._community_guest_mentionable_partners(channel)
        try:
            limit = min(int(limit or GUEST_MENTION_LIMIT), GUEST_MENTION_LIMIT)
        except (TypeError, ValueError):
            limit = GUEST_MENTION_LIMIT
        return super(
            ResPartner, self.with_context(**{GUEST_MENTION_CTX: allowed.ids})
        ).get_mention_suggestions_from_channel(channel_id, search, limit=limit)

    @api.model
    def _community_guest_mentionable_partners(self, channel):
        """The partners a community guest may mention in ``channel``."""
        channels = (channel.parent_channel_id | channel).sudo()
        partners = self.env.user.partner_id
        conversations = channels.filtered(lambda c: c.channel_type != "channel")
        partners |= conversations.channel_member_ids.partner_id
        rooms = channels - conversations
        if rooms:
            groups = (
                self.env["mail.message"]
                .sudo()
                ._read_group(
                    [
                        ("model", "=", "discuss.channel"),
                        ("res_id", "in", rooms.ids),
                        ("message_type", "=", "comment"),
                        ("author_id", "!=", False),
                    ],
                    ["author_id"],
                )
            )
            for (author,) in groups:
                partners |= author
        return partners.sudo(False)

    @api.readonly
    @api.model
    def get_mention_suggestions(self, search, limit=8):
        """Global @-mention search: only people the member converses with.

        Core searches every partner of the database by name or email, which
        would hand a community member the whole directory (staff and
        merchants) with an empty search. A member is only offered the
        members of its own chats and groups.
        """
        if not self.env.user.is_community_member:
            return super().get_mention_suggestions(search, limit=limit)
        allowed = self._community_member_known_partners()
        return super(
            ResPartner, self.with_context(**{GUEST_MENTION_CTX: allowed.ids})
        ).get_mention_suggestions(search, limit=limit)

    @api.readonly
    @api.model
    def search_for_channel_invite(self, search_term, channel_id=None, limit=30):
        """Invite search: same restriction as the global mention search."""
        if not self.env.user.is_community_member:
            return super().search_for_channel_invite(
                search_term, channel_id=channel_id, limit=limit
            )
        allowed = self._community_member_known_partners()
        return super(
            ResPartner, self.with_context(**{GUEST_MENTION_CTX: allowed.ids})
        ).search_for_channel_invite(search_term, channel_id=channel_id, limit=limit)

    @api.model
    def _community_member_known_partners(self):
        """The current user and the members of its chats and groups."""
        user = self.env.user
        seats = (
            self.env["discuss.channel.member"]
            .sudo()
            .search(
                [
                    ("partner_id", "=", user.partner_id.id),
                    ("channel_id.channel_type", "in", ("chat", "group")),
                ]
            )
        )
        partners = user.partner_id | seats.channel_id.channel_member_ids.partner_id
        return partners.sudo(False)

    @api.model
    def _search(self, domain, *args, **kwargs):
        """AND the member restriction into every partner search it scopes.

        Only while ``GUEST_MENTION_CTX`` is in the context, which the
        overrides above set around core's searches. A client sending the key
        itself can only narrow its own results.
        """
        allowed_ids = self.env.context.get(GUEST_MENTION_CTX)
        if allowed_ids is not None:
            domain = Domain(domain) & Domain("id", "in", list(allowed_ids))
        return super()._search(domain, *args, **kwargs)

    @api.model
    def _search_mention_suggestions(self, domain, limit, extra_domain=None):
        allowed_ids = self.env.context.get(GUEST_MENTION_CTX)
        if allowed_ids is not None:
            restrict = Domain("id", "in", list(allowed_ids))
            domain = Domain(domain) & restrict
            if extra_domain:
                extra_domain = Domain(extra_domain) & restrict
        return super()._search_mention_suggestions(domain, limit, extra_domain)
