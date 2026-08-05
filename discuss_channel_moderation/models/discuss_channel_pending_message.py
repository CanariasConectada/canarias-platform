# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

# Bus notification type raised towards the AUTHOR of a held message every time
# its state changes (held / approved / rejected), so their UI can render a
# "waiting for moderation" placeholder or the rejection reason.
BUS_AUTHOR_STATUS = "discuss.channel.moderation/author_status"

MODERATOR_GROUP = "discuss_channel_moderation.group_moderation_user"
MANAGER_GROUP = "discuss_channel_moderation.group_moderation_manager"


class DiscussChannelPendingMessage(models.Model):
    """A comment held before it ever becomes a ``mail.message``.

    WHY a dedicated model instead of a flag on ``mail.message``:

    ``mail.message`` has NO ``ir.rule`` at all. Its access is code-driven in
    ``mail/models/mail_message.py`` (``_search`` at line 317, ``_check_access``
    at line 432) and it is DOCUMENT scoped: ``_find_allowed_doc_ids`` grants a
    reader every message of a document they can read. There is therefore no
    per-message visibility seam -- a "hidden" ``mail.message`` would still be
    readable by every other member of the channel, including the guests we are
    moderating. Holding the payload OUTSIDE ``mail.message`` is the only way to
    make the hold real.

    The same reasoning drives ``mail_group``, the only surviving moderation
    implementation in Odoo 19: it keeps ``moderation_status`` on the wrapper
    model ``mail.group.message`` (``mail_group/models/mail_group_message.py``
    lines 50-56) rather than on ``mail.message``.

    Rows are history: the ACL denies ``create``/``unlink`` to moderators, and
    the module never deletes a decided row.
    """

    _name = "discuss.channel.pending.message"
    _description = "Discuss Channel Pending Message"
    _rec_name = "author_name"
    _order = "id desc"

    channel_id = fields.Many2one(
        comodel_name="discuss.channel",
        string="Channel",
        required=True,
        index=True,
        ondelete="cascade",
    )
    moderation_id = fields.Many2one(
        comodel_name="discuss.channel.moderation",
        string="Moderation",
        required=True,
        index=True,
        ondelete="cascade",
    )
    guest_id = fields.Many2one(
        comodel_name="mail.guest",
        string="Guest Author",
        index=True,
        # set null, NOT cascade: a decided row is history and must outlive the
        # guest record. ``author_name`` below keeps the identity readable.
        ondelete="set null",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Partner Author",
        index=True,
        ondelete="set null",
    )
    author_name = fields.Char(
        string="Author",
        required=True,
        readonly=True,
        help="Snapshot of the author's name taken when the message was held, "
        "so the queue stays readable after a guest is renamed or purged.",
    )
    body = fields.Html(
        string="Message",
        sanitize=True,
        sanitize_tags=True,
        strip_classes=True,
    )
    attachment_ids = fields.Many2many(
        comodel_name="ir.attachment",
        relation="discuss_channel_pending_message_attachment_rel",
        column1="pending_message_id",
        column2="attachment_id",
        string="Attachments",
    )
    parent_id = fields.Many2one(
        comodel_name="mail.message",
        string="Replied To",
        ondelete="set null",
        help="Message this one replies to, kept so an approved reply lands "
        "back under its original anchor.",
    )
    state = fields.Selection(
        selection=[
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        required=True,
        default="pending",
        index=True,
        copy=False,
    )
    message_id = fields.Many2one(
        comodel_name="mail.message",
        string="Published Message",
        readonly=True,
        ondelete="set null",
        copy=False,
        help="The mail.message created on approval. Empty until then.",
    )
    moderator_id = fields.Many2one(
        comodel_name="res.users",
        string="Decided By",
        readonly=True,
        copy=False,
    )
    moderation_date = fields.Datetime(string="Decided On", readonly=True, copy=False)
    late_alert_date = fields.Datetime(
        string="Escalated On",
        readonly=True,
        copy=False,
        help="When the channel's moderators were emailed about this message "
        "still waiting. Set once and never cleared: a moderator who has been "
        "told and has not acted does not need the same email every few "
        "minutes.",
        # Deliberately NOT indexed. The escalation sweep filters on ``state``
        # first, which is indexed, and this column is NULL for almost every row
        # -- a plain btree on it would be a second index of the same rows for
        # nothing. ``index="btree_not_null"`` would be worse still: the query
        # looks for the NULLs, which is exactly what that variant leaves out.
    )
    rejection_reason = fields.Text(
        help="Shown to the author when their message is rejected."
    )

    # The SQL CHECK forbids BOTH authors and nothing else. Written as a plain
    # CHECK because that half must hold even for writes that bypass the ORM. It
    # deliberately does NOT require one of them to be set: ``guest_id`` is
    # ``ondelete='set null'`` and PostgreSQL nulls it out behind the ORM's back
    # when a guest is purged, which a strict XOR check would turn into a crash
    # on guest deletion. Rejecting NEITHER is the ORM's job alone, in
    # ``_check_author_xor`` below -- see ``create`` for why that check needs
    # help to fire at all.
    _author_not_both = models.Constraint(
        "CHECK(NOT (partner_id IS NOT NULL AND guest_id IS NOT NULL))",
        "A held message cannot come from a partner and a guest at the same time.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Force both author fields into ``vals`` so the XOR check always runs.

        ``@api.constrains`` is not a create-time invariant: it only fires for
        the fields actually present in ``vals``. ``create`` builds
        ``data['stored']`` from ``vals.items()`` (``odoo/orm/models.py:4667``)
        and then validates exactly those names (``:4946``). A create that
        mentions neither ``guest_id`` nor ``partner_id`` therefore skipped
        ``_check_author_xor`` entirely and produced an AUTHOR-LESS row, which
        the SQL CHECK happily accepts because it only forbids having both.

        ``_moderation_create_pending`` never does that, but the manager group
        holds create rights on this model, so the hole is reachable over RPC
        from the UI. Seeding both keys (a copy, never a mutation of the
        caller's dict) puts them in ``stored`` whatever their value, which is
        what makes the constraint run on EVERY create. The check itself stays
        the single place where the rule and its message live.
        """
        vals_list = [
            {"guest_id": False, "partner_id": False, **vals} for vals in vals_list
        ]
        return super().create(vals_list)

    @api.constrains("guest_id", "partner_id")
    def _check_author_xor(self):
        """Exactly one author at ORM level (create and write).

        Splits the work with ``_author_not_both``: the SQL CHECK is what
        rejects "both" in practice, because it fires at INSERT time, before the
        ORM ever gets to validate. This check is what rejects "neither" -- the
        case no SQL constraint can express without breaking guest purges. It
        still covers "both" as a second line for ORM writes that never reach a
        fresh INSERT.
        """
        for pending in self:
            if bool(pending.guest_id) == bool(pending.partner_id):
                raise ValidationError(
                    _(
                        "A held message must have exactly one author: a guest or a partner."
                    )
                )

    # ------------------------------------------------------------------
    # Moderation API
    # ------------------------------------------------------------------

    def _check_moderator(self):
        """Explicit moderator check, ON TOP of the record rules.

        Defence in depth: the ``ir.rule`` already scopes the queue per
        moderator, but rules are data and a botched migration or a stray
        ``sudo()`` upstream silently removes them. This check is code, it runs
        first, and it fails loudly.

        There is NO ``sudo``/superuser escape hatch on purpose: ``sudo()`` does
        not change ``env.user`` (``odoo/orm/models.py:5948``), so an internal
        caller that sudo-es its way to this model still has to hold one of the
        two groups. Approving from a script therefore means running as a user
        who is really a moderator -- which is exactly what the audit trail in
        ``moderator_id`` is supposed to mean.
        """
        user = self.env.user
        if user.has_group(MANAGER_GROUP):
            return
        if not user.has_group(MODERATOR_GROUP):
            raise AccessError(_("Only channel moderators can moderate held messages."))
        for pending in self:
            if not pending.moderation_id.sudo()._is_moderator(user):
                raise AccessError(
                    _(
                        "You are not a moderator of the channel %s.",
                        pending.sudo().channel_id.name,
                    )
                )

    def action_approve(self):
        """Publish the held messages. Idempotent: a decided row is skipped."""
        self._check_moderator()
        for pending in self:
            if pending.state != "pending":
                # Approving twice must not post the message twice.
                continue
            message = pending.channel_id.sudo()._post_moderated_message(pending)
            pending.write(
                {
                    "state": "approved",
                    "message_id": message.id,
                    "moderator_id": self.env.uid,
                    "moderation_date": fields.Datetime.now(),
                }
            )
            pending._notify_author()
        return True

    def action_reject(self, reason=None):
        """Discard the held messages. Idempotent: a decided row is skipped.

        No ``mail.message`` is ever created for a rejected row.
        """
        self._check_moderator()
        for pending in self:
            if pending.state != "pending":
                continue
            values = {
                "state": "rejected",
                "moderator_id": self.env.uid,
                "moderation_date": fields.Datetime.now(),
            }
            if reason is not None:
                values["rejection_reason"] = reason
            pending.write(values)
            pending._notify_author()
        return True

    # ------------------------------------------------------------------
    # Bus notifications
    # ------------------------------------------------------------------

    def _moderation_bus_payload(self):
        """Minimal payload: never leaks another persona's data."""
        self.ensure_one()
        return {
            "id": self.id,
            "channel_id": self.channel_id.id,
            "state": self.state,
            "author_name": self.author_name,
            "rejection_reason": self.rejection_reason or "",
            "message_id": self.message_id.id or False,
        }

    def _notify_author(self):
        """Tell the author their message was held / approved / rejected.

        ``mail.guest`` and ``res.partner`` both inherit ``bus.listener.mixin``
        (``mail/models/discuss/mail_guest.py:19`` and
        ``bus/models/res_partner.py:8``), so the same call works for both
        personas.
        """
        pending = self.sudo()
        pending.ensure_one()
        listener = pending.guest_id or pending.partner_id
        if listener:
            listener.sudo()._bus_send(
                BUS_AUTHOR_STATUS, pending._moderation_bus_payload()
            )
