# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Bus notification type raised towards the moderators of a channel when a new
# message lands in their queue. Kept here (and not inlined) so the JS side has a
# single canonical string to listen to.
BUS_NEW_PENDING = "discuss.channel.moderation/new_pending"

# How long a held message may wait before its moderators get an email, in
# MINUTES. Lives in ``ir.config_parameter`` and NOT in a field on this model:
# the delay is a promise made to the visitor ("your comment shows up quickly"),
# and that promise is the platform's, not the channel's. A per-channel field
# would let one channel quietly opt out of the SLA the rest of the site
# advertises, and would need a UI, an ACL and a default on every existing row to
# say the same thing 200 times. The record is shipped in
# ``data/discuss_channel_moderation_params.xml`` so the knob is DISCOVERABLE in
# Settings > Technical > System Parameters; this constant is the fallback for a
# database where it was deleted or set to garbage.
LATE_ALERT_PARAM = "discuss_channel_moderation.late_alert_minutes"
LATE_ALERT_DEFAULT_MINUTES = 30

# The cutoff the cron computed, handed to the mail template through the context
# so the email lists EXACTLY the rows the cron is about to flag as alerted. A
# template that recomputed its own "now" could list a row the cron does not
# flag, and that row would then be announced a second time on the next run.
LATE_ALERT_CUTOFF_CONTEXT = "dcm_late_alert_cutoff"

LATE_ALERT_TEMPLATE = "discuss_channel_moderation.mail_template_late_pending_alert"
PENDING_QUEUE_ACTION = "discuss_channel_moderation.action_pending_message"

# The ONE ``mail.mail.state`` that means "a message was handed to the SMTP
# server and the server took it". Core writes it only after ``send_email``
# returned a message id (``mail/models/mail_mail.py:884-885``); every other
# state is a mail that exists and travelled nowhere. Named here because the
# cron reads it as its definition of "somebody was actually told".
MAIL_SENT_STATE = "sent"


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

    # ------------------------------------------------------------------
    # Late-moderation escalation
    #
    # The bus ping above only reaches a moderator who has Odoo OPEN. The counter
    # on this form only reaches one who comes looking. Neither of them reaches
    # the moderator who went home, which is the only case that matters: the
    # visitor whose comment is still invisible forty minutes later does not come
    # back to check. Everything below exists to turn "nobody looked" into a mail
    # somebody receives.
    # ------------------------------------------------------------------

    @api.model
    def _late_alert_minutes(self):
        """Minutes a held message may wait before its moderators are emailed.

        Reads ``LATE_ALERT_PARAM``. Anything that is not a non-negative integer
        (a typo, an empty string, a deleted parameter) falls back to
        ``LATE_ALERT_DEFAULT_MINUTES`` and says so ONCE per run: a misconfigured
        SLA must not disable the alert, because the failure mode of "no alert"
        is exactly the silence this feature exists to break.

        Zero is accepted and means "alert on the first run that sees the row".
        """
        raw = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(LATE_ALERT_PARAM, LATE_ALERT_DEFAULT_MINUTES)
        )
        try:
            minutes = int(str(raw).strip())
        except (TypeError, ValueError):
            minutes = -1
        if minutes < 0:
            _logger.warning(
                "System parameter %s is %r, which is not a number of minutes. "
                "Falling back to %s minutes for the late-moderation alert.",
                LATE_ALERT_PARAM,
                raw,
                LATE_ALERT_DEFAULT_MINUTES,
            )
            return LATE_ALERT_DEFAULT_MINUTES
        return minutes

    @api.model
    def _late_alert_cutoff(self):
        """Creation date at or before which a pending row counts as late."""
        return fields.Datetime.now() - timedelta(minutes=self._late_alert_minutes())

    @api.model
    def _late_pending_domain(self, cutoff):
        """The ONE definition of "this message has waited too long".

        Written once and used twice -- by the cron, which sweeps every channel,
        and by the mail template, which lists one channel's rows -- so the email
        can never describe a set the cron did not select.

        ``late_alert_date = False`` is what makes the alert fire ONCE per row.
        See ``_cron_alert_late_pending`` for why once is the right number.
        """
        return [
            ("state", "=", "pending"),
            ("late_alert_date", "=", False),
            ("create_date", "<=", cutoff),
        ]

    def _late_alert_cutoff_value(self):
        """The cutoff to use when rendering: the cron's, or a fresh one."""
        return self.env.context.get(
            LATE_ALERT_CUTOFF_CONTEXT
        ) or fields.Datetime.to_string(self._late_alert_cutoff())

    def _late_alert_render_values(self):
        """Everything the mail template needs, in ONE query.

        Returned as a dict rather than as separate methods so the template does
        not have to run the same search three times to say "six messages, the
        oldest waiting 47 minutes, here they are".
        """
        self.ensure_one()
        messages = (
            self.env["discuss.channel.pending.message"]
            .sudo()
            .search(
                self._late_pending_domain(self._late_alert_cutoff_value())
                + [("moderation_id", "=", self.id)],
                order="create_date asc",
            )
        )
        oldest_minutes = 0
        if messages:
            waited = fields.Datetime.now() - messages[0].create_date
            oldest_minutes = int(waited.total_seconds() // 60)
        base_url = (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url", "") or ""
        )
        return {
            "messages": messages,
            "count": len(messages),
            "oldest_minutes": oldest_minutes,
            # Odoo 19 resolves an action by xmlid in the URL itself
            # (``/odoo/<path:subpath>``, web/controllers/home.py:47), so the
            # link survives a reinstall that renumbers the action.
            "queue_url": "%s/odoo/action-%s" % (base_url, PENDING_QUEUE_ACTION),
        }

    def _late_alert_send(self, template):
        """Send this channel's alert and report whether it REALLY went out.

        Returns an empty string when a message reached the mail server, and a
        short human-readable reason when it did not, so the caller can log the
        failure and leave the rows unflagged for the next run.

        WHY ``raise_exception=True`` IS NOT ENOUGH, and why this method exists.
        A ``mail.mail`` whose recipients resolve to nothing raises NOTHING:
        core marks the row ``state='exception'`` /
        ``failure_type='mail_email_missing'``, then iterates an EMPTY
        ``email_list`` (``mail/models/mail_mail.py:823-883``), never touches the
        SMTP server and returns normally. The ``try/except`` around the send saw
        a clean return and the cron stamped every row as announced -- the exact
        silent loss this escalation exists to break, reproduced in production
        for as long as the template shipped without ``use_default_to=False``.
        The same shape covers an address that is present but unusable
        (``mail_email_invalid``), which no exception reports either. So the
        check here is on the RESULT, not on the absence of an exception.

        WHY ``auto_delete`` IS TURNED OFF FOR THIS SEND. With it on, the row
        deletes itself both when the mail is sent and when it is discarded for
        want of recipients (``mail/models/mail_mail.py:281-282``): "the record
        is gone" cannot tell success from failure, and a check that cannot tell
        them apart is not a check. It is switched off, the state is read, and
        the row is deleted here by hand -- which keeps the template's promise
        that this alert leaves no queue behind. That promise matters more than
        the forensic value of a failed row: the cron runs every five minutes,
        so a kept row per failed pass would rebuild the pile of stuck mails
        this deployment already had once. What survives a failure is the ERROR
        in the log, which carries the state and the reason.

        Mails that failed with an exception are NOT deleted, here or before
        this change: the raise short-circuits this method and core keeps rows
        whose ``failure_type`` is neither missing nor invalid.
        """
        self.ensure_one()
        mail = (
            self.env["mail.mail"]
            .sudo()
            .browse(
                template.send_mail(
                    self.id,
                    force_send=True,
                    raise_exception=True,
                    email_values={"auto_delete": False},
                )
            )
            .exists()
        )
        if not mail:
            # Nothing legitimate deletes the row now that auto_delete is off,
            # so this is somebody else's cleanup racing the cron. Reported like
            # any other non-delivery rather than assumed to have worked.
            return "the mail.mail record disappeared before its state was read"
        state, failure_type, failure_reason = (
            mail.state,
            mail.failure_type,
            mail.failure_reason,
        )
        mail.unlink()
        if state == MAIL_SENT_STATE:
            return ""
        return "state %r, failure type %r (%s)" % (
            state,
            failure_type or "none recorded",
            failure_reason or "no reason recorded",
        )

    @api.model
    def _cron_alert_late_pending(self):
        """Email the moderators of every channel sitting on an overdue queue.

        ONE MAIL PER CHANNEL, never one per message. Six held comments are one
        problem with six lines in it, and six separate emails are how a useful
        alert becomes a filter rule. The audit that preceded this module already
        flagged notification amplification on this platform; a per-row mail
        would recreate it in the one place designed to fix it.

        ONE MAIL PER ROW, EVER. A row that has been announced is stamped with
        ``late_alert_date`` and never enters another email. The alternative --
        re-alerting every run -- tells a moderator who already knows something
        they already know, every few minutes, until they mute the sender; the
        alert would then be loudest exactly when it stops being read. What keeps
        a busy channel audible is that each NEW message earns its own first
        alert, so an actually-active queue keeps producing mail while an
        abandoned single message goes quiet. The limit of that trade-off is
        written down in ``readme/ROADMAP.md``: one message stuck on a dead
        channel is announced once and then never again, and only the warning
        below covers the "nobody is listening at all" case.

        Failures are LOUD and NOT final: the row is stamped only after a
        message has been PROVED to leave, so a channel whose mail bounced is
        retried on the next run instead of being silently marked as handled.
        This deployment has had hundreds of messages sit unsent in the queue
        with nobody noticing, and an escalation that quietly joins that pile is
        worse than no escalation, because it reads as covered.

        THREE WAYS TO REACH NOBODY, THREE MESSAGES, because they are fixed in
        three different places: assign a moderator, fill in an address, repair
        the mail configuration or the template. ``raise_exception=True`` only
        covers the fourth (a send that blows up); the third is caught by
        ``_late_alert_send``, which reads the state of the ``mail.mail`` instead
        of trusting that no exception means success.

        Nothing is logged on the happy path: this database has no log rotation,
        and a cron that prints a line per handled row would be the next thing to
        fill the disk.
        """
        cutoff = self._late_alert_cutoff()
        late = (
            self.env["discuss.channel.pending.message"]
            .sudo()
            .search(
                self._late_pending_domain(cutoff)
                # An archived configuration is a channel that was taken off
                # moderation: its leftover rows still need a human decision (see
                # ROADMAP) but nobody is on the hook for them within 30 minutes.
                + [("moderation_id.active", "=", True)]
            )
        )
        if not late:
            return
        template = self.env.ref(LATE_ALERT_TEMPLATE, raise_if_not_found=False)
        if not template:
            # Not a warning: without the template the feature is OFF, which is
            # the thing the whole module is trying not to be silent about.
            _logger.error(
                "Mail template %s is missing: %s message(s) are past the "
                "moderation SLA and no moderator can be alerted.",
                LATE_ALERT_TEMPLATE,
                len(late),
            )
            return
        template = template.sudo().with_context(
            **{LATE_ALERT_CUTOFF_CONTEXT: fields.Datetime.to_string(cutoff)}
        )
        alerted_at = fields.Datetime.now()
        for moderation, pendings in late.grouped("moderation_id").items():
            moderation = moderation.sudo()
            moderators = moderation.moderator_user_ids
            # A moderated channel with nobody on it is a queue that fills
            # forever. Naming it is the whole point: an admin reading the log
            # can fix it, an admin reading "0 mails sent" cannot.
            if not moderators:
                _logger.warning(
                    "Moderated channel %r (moderation id %s) has %s message(s) "
                    "past the %s-minute moderation SLA and NO moderator to "
                    "alert. Nobody can empty this queue.",
                    moderation.channel_id.name,
                    moderation.id,
                    len(pendings),
                    self._late_alert_minutes(),
                )
                continue
            if not moderators.filtered("email"):
                # Distinct from the case above on purpose: "there is nobody" and
                # "there is somebody with no address" are fixed differently.
                _logger.warning(
                    "Moderated channel %r (moderation id %s) has %s message(s) "
                    "past the moderation SLA and none of its %s moderator(s) "
                    "has an email address.",
                    moderation.channel_id.name,
                    moderation.id,
                    len(pendings),
                    len(moderators),
                )
                continue
            try:
                undelivered = moderation._late_alert_send(template)
            except Exception:
                # Poison-record isolation: one channel whose mail blew up must
                # not cost the other channels their alert. ``exception`` and not
                # ``warning`` because the traceback is the only thing that says
                # WHY nothing arrived.
                _logger.exception(
                    "Late-moderation alert failed for channel %r (moderation "
                    "id %s); its %s message(s) stay unflagged and will be "
                    "retried on the next run.",
                    moderation.channel_id.name,
                    moderation.id,
                    len(pendings),
                )
                continue
            if undelivered:
                # The third silence, and the one that used to pass for success:
                # there ARE moderators, they DO have addresses, the send raised
                # nothing -- and no message left the machine. Distinct from the
                # two warnings above because it is not fixed by touching this
                # channel: it points at the template's recipient expression or
                # at the outgoing mail configuration.
                _logger.error(
                    "Late-moderation alert for channel %r (moderation id %s) "
                    "reached its %s moderator(s) on paper and DELIVERED "
                    "NOTHING: %s. Its %s message(s) stay unflagged and will be "
                    "retried on the next run.",
                    moderation.channel_id.name,
                    moderation.id,
                    len(moderators),
                    undelivered,
                    len(pendings),
                )
                continue
            pendings.write({"late_alert_date": alerted_at})
