# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

# Bus notification type raised towards the moderators of a channel when a new
# message lands in their queue. Kept here (and not inlined) so the JS side has a
# single canonical string to listen to.
BUS_NEW_PENDING = "discuss.channel.moderation/new_pending"


class DiscussChannelModeration(models.Model):
    """Per-channel pre-moderation switch.

    One row per moderated channel. The row is the *only* thing that turns the
    hold on: no context key, no ``ir.config_parameter``, no route flag. The
    shape (a small side model plus an explicit ``moderator_user_ids`` list) is
    copied from ``mail_group`` -- the only moderation implementation that
    survived in Odoo 19 -- see ``mail_group/models/mail_group.py:63-68``.

    The model knows nothing about zones, websites or companies on purpose: it
    is a generic gate over ``discuss.channel``.
    """

    _name = "discuss.channel.moderation"
    _description = "Discuss Channel Moderation"
    _rec_name = "channel_id"
    _order = "id desc"

    channel_id = fields.Many2one(
        comodel_name="discuss.channel",
        string="Channel",
        required=True,
        index=True,
        ondelete="cascade",
    )
    active = fields.Boolean(
        default=True,
        help="Archive the configuration to stop holding messages on this "
        "channel without losing the moderation history.",
    )
    moderate_guests = fields.Boolean(
        string="Moderate Guests",
        default=True,
        help="Hold every comment posted by an anonymous visitor until a "
        "moderator approves it.",
    )
    moderate_portal = fields.Boolean(
        string="Moderate Portal Users",
        default=False,
        help="Also hold the comments of logged-in portal users. Internal "
        "users are never moderated.",
    )
    moderator_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="discuss_channel_moderation_user_rel",
        column1="moderation_id",
        column2="user_id",
        string="Moderators",
        help="Users allowed to approve or reject the messages held on this "
        "channel. They see this channel's queue and no other.",
    )
    pending_message_ids = fields.One2many(
        comodel_name="discuss.channel.pending.message",
        inverse_name="moderation_id",
        string="Held Messages",
    )
    pending_count = fields.Integer(
        string="Pending",
        compute="_compute_pending_count",
        compute_sudo=True,
        help="Messages currently waiting for a decision.",
    )

    _channel_uniq = models.Constraint(
        "unique(channel_id)",
        "This channel already has a moderation configuration.",
    )

    @api.depends("pending_message_ids.state")
    def _compute_pending_count(self):
        # compute_sudo: the badge must be right even when read by someone who
        # cannot see the individual held messages (the record rule scopes the
        # queue per moderator, the count is only an aggregate).
        counts = dict(
            self.env["discuss.channel.pending.message"]._read_group(
                [("moderation_id", "in", self.ids), ("state", "=", "pending")],
                ["moderation_id"],
                ["__count"],
            )
        )
        for moderation in self:
            moderation.pending_count = counts.get(moderation, 0)

    @api.model
    def _get_for_channel(self, channel):
        """Return the ACTIVE moderation row governing ``channel``, or empty.

        ``sudo`` because the caller is, by construction, an untrusted persona
        (a guest or a portal user) posting a message: it has no read access to
        this model and must not get any. The returned record is only used to
        decide whether to hold, never handed back to the caller.

        ``active`` is a plain ``active`` field, so an archived configuration is
        filtered out by the ORM's default active test: archiving the row is the
        documented way of switching moderation off.

        MODERATION IS INHERITED BY SUB-CHANNELS. The lookup used to match
        ``channel_id`` exactly, which made a thread opened under a moderated
        channel an unmoderated space: ``/discuss/channel/sub_channel/create``
        creates a ``discuss.channel`` whose ``group_public_id`` is COPIED from
        the parent (``mail/models/discuss/discuss_channel.py:351-357``), so the
        very visitors held on the parent can read the child -- and post there
        with nothing in the way. Creating the sub-channel needs write rights the
        untrusted personas do not have (``base.group_public`` and
        ``base.group_portal`` are ``1,0,0,0`` on ``discuss.channel``,
        ``mail/security/ir.model.access.csv:13-14``), so it takes one internal
        user clicking "open a thread" to hand them the room; nothing about that
        click says "and drop the moderation".

        The walk is ONE level because core allows exactly one: a channel whose
        parent already has a parent is rejected by
        ``_constraint_parent_channel_id``
        (``mail/models/discuss/discuss_channel.py:151-159``). A loop here would
        be dead code pretending to handle a depth the database refuses.

        A row on the sub-channel itself WINS over the parent's, so a thread can
        still be given its own moderators, or be exempted by archiving its own
        row, without touching the parent.
        """
        if not channel:
            return self.browse()
        moderation = self.sudo().search([("channel_id", "=", channel.id)], limit=1)
        if moderation:
            return moderation
        # sudo: same reason as above; ``parent_channel_id`` is not readable by
        # the persona whose post is being classified.
        parent = channel.sudo().parent_channel_id
        if not parent:
            return self.browse()
        return self.sudo().search([("channel_id", "=", parent.id)], limit=1)

    def _is_moderator(self, user=None):
        """Whether ``user`` (default: current user) moderates this channel."""
        self.ensure_one()
        user = user or self.env.user
        return user in self.sudo().moderator_user_ids

    def _notify_moderators(self, pending):
        """Push a bus notification to every moderator of this channel.

        Sent per user (``res.users`` inherits ``bus.listener.mixin`` through
        ``bus/models/res_users.py``) so a moderator gets the ping wherever they
        are, without subscribing them to the channel itself.
        """
        self.ensure_one()
        payload = pending.sudo()._moderation_bus_payload()
        for user in self.sudo().moderator_user_ids:
            user.sudo()._bus_send(BUS_NEW_PENDING, payload)
