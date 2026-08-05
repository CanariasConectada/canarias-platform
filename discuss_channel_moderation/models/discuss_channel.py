# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import Command, _, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext, is_html_empty

# Where an attachment lives while the message it belongs to is HELD. It is a
# real model of this module, so the attachment's own ACL check
# (``ir.attachment._check_access`` -> ``_inaccessible_comodel_records``, which
# ends in ``_filtered_access`` on the referenced record) resolves to "can this
# user read that held message?". A moderator can, a third party cannot, and
# nobody had to write a second access policy for binaries.
HELD_ATTACHMENT_MODEL = "discuss.channel.pending.message"

# The placeholder shape core itself gives to a not-yet-posted composer upload
# (``mail/controllers/attachment.py:61-69``). It is the ONLY shape
# ``_process_attachments_for_post`` (``mail/models/mail_thread.py:2410-2416``)
# agrees to transfer onto a message for a non-internal caller, so it is also
# the shape a held attachment must be put back into just before publication.
DRAFT_ATTACHMENT_MODEL = "mail.compose.message"

# Ceilings applied to what an UNTRUSTED persona can leave in the queue. They
# are not rate limiting -- see readme/ROADMAP.md -- they only stop a single
# request, or a single persona, from turning the queue into a dump.
MAX_HELD_BODY_LENGTH = 64 * 1024
MAX_PENDING_PER_PERSONA = 20

# The ONE ``message_type`` a moderated message is ever published with. Pinned
# here, as a constant, because the value that reaches ``message_post`` on the
# public route comes straight from attacker-supplied ``post_data``
# (``mail/controllers/thread.py:149-155`` copies every key of
# ``_get_allowed_message_params``, and ``message_type`` is one of them). A held
# message is by definition a visitor comment; publishing it as anything else
# would let the author pick how the platform treats their own text (whether it
# counts towards ``message_count``, whether it is mailed out, which subtype it
# carries). The held row therefore never stores the incoming type, and the
# publication path never reads one.
MODERATED_MESSAGE_TYPE = "comment"
MODERATED_MESSAGE_SUBTYPE = "mail.mt_comment"

# The class core wraps EVERY in-thread system event in -- joined, left,
# renamed, pinned, call started (``mail/models/discuss/discuss_channel.py:579``,
# ``:665``, ``:1128``, ``:1467`` and
# ``mail/models/discuss/discuss_channel_rtc_session.py:52``). Used, together
# with "and it renders to no text at all", to recognise a body that carries
# nobody's words -- see ``_moderation_is_contentless_notice``.
SYSTEM_NOTICE_MARKER = "o_mail_notification"


class DiscussChannel(models.Model):
    """The body gate. One of several; the module no longer claims otherwise.

    ``message_post`` is the ONE funnel for CREATING a ``mail.message``, and the
    first version of this module stopped there and documented itself as "THE
    funnel". Three rounds of adversarial validation on a copy of production
    falsified that sentence three times, each time through a surface that never
    calls ``message_post``: ``message_type`` steering the gate, then uploads /
    edits / reactions / guest names, then link previews. What survived is not
    "one funnel" but a list -- and the list, with what is deliberately NOT on
    it, is written down in ``readme/DESCRIPTION.md``. Keeping that list honest
    is the maintenance obligation this module carries.

    WHERE THE GATES ARE, and which question each one asks:

    - ``discuss.channel.message_post`` -- the body. PERSONA question.
    - ``discuss.channel._message_update_content`` -- the body of an already
      published message. PERSONA question. ``_can_edit_message``
      (``mail/controllers/thread.py:253``) grants the edit to
      ``is_current_user_or_guest_author``, and after approval the guest IS the
      author, so "approve once, then rewrite" published arbitrary text with no
      second decision.
    - ``ir.attachment.create`` -- the bytes. PERSONA question.
      ``/mail/attachment/upload`` (``auth="public"``) wrote
      ``res_model='discuss.channel'`` on its own and
      ``/discuss/channel/attachments`` served it, ``raw_access_token``
      included, with no message and no held row in sight.
    - ``ir.attachment.write`` / ``unlink`` -- the held EVIDENCE. Internal-only,
      because the uploader keeps their ownership token after the file is
      re-parented and used it to delete the moderator's evidence.
    - ``mail.message._message_reaction`` -- the reaction. PERSONA question:
      core stores any string of any length and serves it to every reader.
    - ``mail.guest.create`` / ``_update_name`` -- the byline. Sanitised for
      EVERY guest, not only moderated ones.
    - ``mail.link.preview`` / ``mail.message.link.preview`` -- the preview
      card. CHANNEL question, and the one deliberate exception to "the persona
      decides"; ``mail_link_preview.py`` explains why a persona rule cannot
      work there.

    WHAT IS EXPLICITLY OUT OF SCOPE, so round four does not spend time on it:
    anything outside ``discuss.channel``; internal users, who are never held;
    portal users unless ``moderate_portal`` is on; rate limiting; and channel
    METADATA (name, avatar, description), which is writable only by users who
    already hold write access on the channel -- an untrusted persona has none
    (``mail/security/ir.model.access.csv:13-14``).

    Gates stay on models, never on controllers, so a new route, a new widget or
    a raw RPC call cannot route around them.
    """

    _inherit = "discuss.channel"

    # ------------------------------------------------------------------
    # The gate
    # ------------------------------------------------------------------

    def message_post(self, *, message_type="notification", **kwargs):
        """Hold the comment instead of posting it when the author is untrusted.

        Returns an EMPTY ``mail.message`` recordset when the message is held --
        never a half-built message. The public caller
        ``/mail/message/post`` reads ``message.id`` (``False`` on an empty
        recordset, ``odoo/orm/fields_misc.py:110``) and feeds the recordset to
        ``Store.add``, which no-ops on an empty set
        (``mail/tools/discuss.py:100``), so an empty return is a clean "nothing
        was published" for the client.

        ``message_type`` is accepted (and forwarded to ``super``) but plays NO
        part in the hold decision -- see ``_moderation_hold``.
        """
        moderation = self._moderation_hold()
        if moderation:
            if self._moderation_is_contentless_notice(
                kwargs.get("body"), kwargs.get("attachment_ids")
            ):
                return self.env["mail.message"]
            self._moderation_create_pending(moderation, **kwargs)
            return self.env["mail.message"]
        return super().message_post(message_type=message_type, **kwargs)

    @staticmethod
    def _moderation_is_contentless_notice(body, attachment_ids):
        """A system event with no words in it: publish nothing, queue nothing.

        THE noise this removes: a guest joining a call makes core post
        ``<div data-oe-type="call" class="o_mail_notification"></div>``
        (``mail/models/discuss/discuss_channel_rtc_session.py:52``) through
        ``message_post`` as the guest persona, so it was held like a comment.
        That is wrong in both directions. Approving it posts a "call started"
        notice for a call that ended while the row sat in the queue -- the
        moderator's decision manufactures a lie. Rejecting it is the only sane
        outcome, and until someone gets round to it the row eats one of the 20
        slots ``MAX_PENDING_PER_PERSONA`` reserves for content a human actually
        has to read.

        Dropping it hides nothing: the call is broadcast to every member over
        the bus by that same ``create``, message or no message.

        WHY MATCHING ON THE BODY IS NOT ROUND ONE ALL OVER AGAIN. The earlier
        bypass read an attacker-supplied ``message_type`` and, on a match, took
        the branch that PUBLISHES. This reads an attacker-suppliable body and,
        on a match, takes the branch that publishes NOTHING. A forger can use
        it to have their own post silently discarded, which is a strictly worse
        outcome for them than the queue. A discriminator is only dangerous when
        the branch it selects is the permissive one.

        The test is narrow on purpose -- core's system-notice wrapper AND no
        rendered text AND no attachments -- so it cannot swallow anything a
        human typed. Text-bearing notices (joined, left, renamed) still go
        through the queue, because their text embeds a persona-controlled name.
        """
        if attachment_ids:
            return False
        body = str(body or "")
        if SYSTEM_NOTICE_MARKER not in body:
            return False
        return not html2plaintext(body).strip()

    def _moderation_hold(self):
        """Return the moderation row that must swallow this post, or empty.

        TAKES NO ARGUMENT ON PURPOSE. Everything ``message_post`` receives on
        the public route is attacker-supplied: ``_prepare_message_data``
        (``mail/controllers/thread.py:149-155``) copies out of ``post_data``
        every key listed by ``mail.thread._get_allowed_message_params``
        (``mail/models/mail_thread.py:5073-5078``), and that list contains
        ``message_type``. A gate that reads any of those values can be steered
        by the very persona it is meant to moderate, so this method reads
        nothing but ``self`` (persistent data) and the session identity.

        Deliberately consults NO context key either.
        ``mail/controllers/thread.py:205`` runs
        ``request.update_context(**context)`` inside an ``auth="public"``
        route, so every context key is attacker-controlled as well.

        Identity is read through ``res.partner._get_current_persona()``
        (``mail/models/res_partner.py:340``), which still returns the guest
        inside a ``sudo()``-ed post because ``sudo()`` does not change
        ``env.user`` (``odoo/orm/models.py:5948-5951``) -- and the public routes
        always post sudo-ed.

        PERSONA FIRST -- and that ordering is the whole point. An earlier
        version short-circuited on ``message_type != "comment"``, on the theory
        that only comments come from visitors. They do not: a visitor picks the
        type. That early return left every other value in the selection
        (``notification``, ``email``, ``email_outgoing``, ``auto_comment``,
        ``user_notification``, plus whatever ``sms``/``snailmail`` and friends
        add) as an open door, publishing the visitor's HTML into the channel
        with one extra key in ``post_data``.

        Now the persona decides alone. An untrusted author is held whatever the
        post claims to be; a trusted one -- an internal user, which is what
        server-generated join notices, renames and tracking messages run as --
        is never held, so by the time the message type could possibly matter
        there is nothing left to decide. That is why no ``message_type`` test
        survives here: on the untrusted branch it would be a bypass, and on the
        trusted branch it would be dead code.
        """
        self.ensure_one()
        moderation_model = self.env["discuss.channel.moderation"]
        moderation = moderation_model._get_for_channel(self)
        if not moderation:
            return moderation_model
        partner, guest = self.env["res.partner"]._get_current_persona()
        if guest or self.env.user._is_public():
            # A public session with no guest cookie is treated as a guest too:
            # it is strictly less identified, not more trusted.
            return moderation if moderation.moderate_guests else moderation_model
        if partner and self.env.user._is_portal():
            return moderation if moderation.moderate_portal else moderation_model
        # Internal users (moderators included) are never held.
        return moderation_model

    def _moderation_create_pending(
        self,
        moderation,
        *,
        body="",
        parent_id=False,
        attachment_ids=None,
        **kwargs,
    ):
        """Store the message out of reach of ``mail.message`` and notify.

        Only the moderatable payload survives (body, attachments, parent).
        Everything else the caller passed is dropped on purpose: recipients,
        subtypes and notification kwargs are re-derived at publication time by
        the core ``message_post``, so nothing an untrusted caller sent can ride
        along to the moment the message becomes real.

        ``message_type`` is part of that dropped remainder: it is swallowed by
        ``**kwargs`` and never stored, so there is no field for an attacker's
        value to hide in until approval. Publication always uses
        ``MODERATED_MESSAGE_TYPE``.

        This is also the ONE place a held row is born -- the public post and
        the held edit both land here -- which is why the volume ceilings and
        the attachment hand-over live here and not in ``message_post``.
        """
        self.ensure_one()
        partner, guest = self._moderation_persona()
        self._moderation_check_quota(partner, guest, body)
        author_name = (guest.sudo().name if guest else partner.sudo().name) or _(
            "Anonymous"
        )
        # sudo: the author is by definition a persona with no rights on this
        # model, and must not be granted any.
        pending = (
            self.env["discuss.channel.pending.message"]
            .sudo()
            .create(
                {
                    "channel_id": self.id,
                    "moderation_id": moderation.id,
                    "guest_id": guest.id,
                    "partner_id": False if guest else partner.id,
                    "author_name": author_name,
                    "body": body or "",
                    "parent_id": parent_id or False,
                    "attachment_ids": [Command.set(list(attachment_ids or []))],
                }
            )
        )
        self._moderation_hold_attachments(pending)
        pending._notify_author()
        moderation._notify_moderators(pending)
        return pending

    def _moderation_persona(self):
        """The author of the post, with the public partner as last resort.

        A public session with no guest cookie has neither partner nor guest.
        The row must still have exactly one author (``_check_author_xor``), and
        the quota below must still have something to count, so the public
        partner stands in. See ROADMAP for what that shared bucket means.
        """
        partner, guest = self.env["res.partner"]._get_current_persona()
        if not guest and not partner:
            partner = self.env.user.sudo().partner_id
        return partner, guest

    def _moderation_check_quota(self, partner, guest, body):
        """Bound one request, and one persona, BEFORE the row exists.

        Held content is content nobody is looking at yet, which is exactly what
        makes it a comfortable place to dump things: the validation stored a
        2 MB body and could have stored any number of them. Two ceilings, both
        refused with a message the author actually sees (``UserError`` comes
        back as the error payload of the ``auth="public"`` JSON route).

        The count is per persona AND per channel on purpose. Per persona alone
        would be stricter, but the cookie-less visitor is authored by the ONE
        public partner shared by every anonymous session on the platform, so a
        platform-wide count would let one flooder lock anonymous posting
        everywhere. Scoping it to the channel keeps the blast radius on the
        channel being flooded, which is also the channel a moderator is
        watching.
        """
        self.ensure_one()
        if len(body or "") > MAX_HELD_BODY_LENGTH:
            raise UserError(
                _(
                    "Your message is too long to be reviewed (%(limit)s characters "
                    "maximum). Please shorten it and try again.",
                    limit=MAX_HELD_BODY_LENGTH,
                )
            )
        author_domain = (
            [("guest_id", "=", guest.id)]
            if guest
            else [("partner_id", "=", partner.id)]
        )
        # sudo: the author has no rights on the queue and must not get any;
        # only the COUNT of their own held rows is read here.
        outstanding = (
            self.env["discuss.channel.pending.message"]
            .sudo()
            .search_count(
                [("channel_id", "=", self.id), ("state", "=", "pending")]
                + author_domain,
                limit=MAX_PENDING_PER_PERSONA + 1,
            )
        )
        if outstanding >= MAX_PENDING_PER_PERSONA:
            raise UserError(
                _(
                    "You already have %(limit)s messages waiting for review on this "
                    "channel. Please wait until they are reviewed before posting "
                    "again.",
                    limit=MAX_PENDING_PER_PERSONA,
                )
            )

    # ------------------------------------------------------------------
    # Attachments of a held message
    # ------------------------------------------------------------------

    def _moderation_hold_attachments(self, pending):
        """Move the held message's files OFF the channel and ONTO the held row.

        The leak this closes: ``/discuss/channel/attachments`` searches on
        ``res_model``/``res_id`` alone (``mail/controllers/discuss/channel.py:166-173``)
        and knows nothing about messages, so an attachment sitting on the
        channel is served -- with the ``raw_access_token`` that
        ``ir.attachment._to_store_defaults`` puts in the payload
        (``mail/models/ir_attachment.py:100``) -- to anyone who asks, published
        message or not. Re-parenting the file to the held row makes that route
        structurally unable to return it, instead of asking every reader to
        remember to filter.

        Only attachments that belong to NO ``mail.message`` are taken. The ids
        reaching a hold come from caller-supplied ``attachment_ids``, and while
        the public route does check ownership before forwarding them
        (``_prepare_message_data``, ``mail/controllers/thread.py:156-162``),
        re-parenting a file that is already part of a published message would
        turn this into a way of REMOVING someone else's content from a channel.

        Files ALREADY parented to another held row are skipped for the same
        reason, one step earlier: their uploader keeps the ownership token, so
        they can send the same id in a second post, and moving it would empty
        the first row's evidence. Skipping here also keeps
        ``ir.attachment._moderation_check_evidence`` from firing on the
        module's own flow -- the guard exists for the author, not for us.
        """
        self.ensure_one()
        attachments = pending.sudo().attachment_ids
        if not attachments:
            return attachments
        published = (
            self.env["mail.message"]
            .sudo()
            .search([("attachment_ids", "in", attachments.ids)])
        )
        already_held = attachments.filtered(
            lambda attachment: attachment.res_model == HELD_ATTACHMENT_MODEL
        )
        holdable = attachments - published.attachment_ids - already_held
        holdable.sudo().write(
            {"res_model": HELD_ATTACHMENT_MODEL, "res_id": pending.id}
        )
        return holdable

    def _moderation_park_attachments(self, attachments):
        """Put files back in the draft shape, i.e. attached to nothing public.

        Used when a published message is withdrawn: its files must stop being
        channel attachments at the same instant its body stops being served,
        or the withdrawal only hides the text.
        """
        attachments.sudo().write({"res_model": DRAFT_ATTACHMENT_MODEL, "res_id": 0})

    def _moderation_release_attachments(self, message):
        """Hand the held files over to the message that was just published.

        Two steps because core meets us half-way and no further:
        ``_process_attachments_for_post`` only re-parents attachments already
        in the draft shape AND created by the current user, and for a
        non-internal caller it silently DROPS everything else
        (``mail/models/mail_thread.py:2410-2416``). The guest branch of
        ``_post_moderated_message`` posts as the public user, so the files have
        to be back in that shape before the post or they never reach the
        message; the portal branch posts as the moderator, where core keeps the
        ids but re-parents nothing, so the link is finished by hand afterwards.
        """
        self.ensure_one()
        stale = message.sudo().attachment_ids.filtered(
            lambda attachment: attachment.res_model == DRAFT_ATTACHMENT_MODEL
        )
        stale.sudo().write({"res_model": self._name, "res_id": self.id})

    # ------------------------------------------------------------------
    # Editing an already published message
    # ------------------------------------------------------------------

    def _message_update_content(
        self, message, /, *, body=None, attachment_ids=None, **kwargs
    ):
        """An untrusted edit re-enters the queue instead of publishing.

        THE bypass this closes: the module used to touch nothing on this path,
        and the path is wide open by design. ``/mail/message/update_content``
        is ``auth="public"`` and its guard, ``_can_edit_message``
        (``mail/controllers/thread.py:253``), grants the edit to
        ``message.sudo().is_current_user_or_guest_author``. After approval the
        guest IS the author, so one approved message was a permanent licence to
        publish anything: the validation rewrote an approved body to arbitrary
        spam, HTTP 200, no new hold, and both a guest and an anonymous visitor
        were served the new text.

        Held rather than refused, because refusing would need its own answer
        for a persona whose message is legitimately being corrected, and would
        leave the module with two ways of saying no. Holding reuses the one
        path that already exists: the edit becomes a normal held row, the
        moderator sees the new text next to the old decision, and approving it
        publishes a new message.

        Withdrawing the published message is half the fix and not a detail:
        while the edit waits, the OLD body must stop being served too --
        otherwise "your edit is under review" would still leave the previous
        text in front of everyone, and an author who edits to remove something
        would be worse off than one who never edited.

        A pure DELETION (empty body, no attachments) is not held: it publishes
        nothing, and turning "remove my message" into a moderation task would
        both queue empty rows and make deletion slower than posting.
        """
        moderation = self._moderation_hold()
        if not moderation:
            return super()._message_update_content(
                message, body=body, attachment_ids=attachment_ids, **kwargs
            )
        message_sudo = message.sudo()
        # ``None`` means "no update" in core, so the message's own content is
        # what the edit leaves in place, and that is what has to be re-reviewed.
        new_body = message_sudo.body if body is None else body
        carried = message_sudo.attachment_ids
        new_attachments = (
            carried.ids if attachment_ids is None else list(attachment_ids)
        )
        parent_id = message_sudo.parent_id.id
        self._moderation_withdraw_message(message_sudo, carried)
        if is_html_empty(new_body) and not new_attachments:
            return None
        self._moderation_create_pending(
            moderation,
            body=new_body,
            parent_id=parent_id,
            attachment_ids=new_attachments,
        )
        return None

    def _moderation_withdraw_message(self, message, attachments):
        """Unpublish: empty the body, detach the files, park them off-channel.

        Done through core's own empty-body branch of ``_message_update_content``
        (``mail/models/mail_thread.py:4943`` writes ``body = ""``, then
        ``_filter_empty``/``_clean_empty_message`` tidy up and the ``Store``
        update goes out on the bus) so a withdrawn message reaches every client
        exactly like a deleted one. ``strict=False`` skips
        ``_check_can_update_message_content``: that check exists to protect the
        AUTHOR's edits, and this is the module withdrawing a message it
        published itself, always with ``MODERATED_MESSAGE_TYPE``.

        The attachments are detached FIRST because that same core branch would
        otherwise ``_delete_and_notify()`` them, and they are the evidence the
        moderator needs to decide on the edit.
        """
        self.ensure_one()
        if attachments:
            message.attachment_ids = [Command.clear()]
            self._moderation_park_attachments(attachments)
        # ``attachment_ids=None`` is core's "do not touch them", which is what
        # keeps the line above from being undone by a delete.
        super(DiscussChannel, self.sudo())._message_update_content(
            message, body="", attachment_ids=None, strict=False
        )

    # ------------------------------------------------------------------
    # Publication
    # ------------------------------------------------------------------

    def _post_moderated_message(self, pending):
        """Publish a held message on this channel. PRIVATE ON PURPOSE.

        Private (leading underscore) because it is the single code path in the
        module that writes a ``mail.message`` WITHOUT passing the moderation
        gate. A public method would be callable over RPC by anyone with write
        access to the model and would hand them a turnkey bypass of the whole
        feature. Its only legitimate caller is
        ``discuss.channel.pending.message.action_approve``, which runs
        ``_check_moderator()`` and the record rules first.

        It calls ``super(DiscussChannel, channel).message_post(...)``, i.e. it
        jumps explicitly PAST this class to the core
        ``discuss.channel.message_post``. If it called plain
        ``channel.message_post(...)`` the override above would re-fire and the
        approval would create a second pending row instead of a message.
        Everything below us in the MRO (the core channel logic, then
        ``mail.thread``) still runs untouched.

        Guest attribution cannot be done by passing ``author_guest_id``:
        ``mail/models/mail_thread.py:2303`` overwrites whatever the caller sent
        with the value computed at lines 2271-2277, which derives the guest
        author from ``env.user._is_public()`` plus the context guest. The
        supported way -- and the exact shape the ``auth="public"`` routes
        produce -- is therefore to impersonate the public user with the guest
        in context. Partners keep the ordinary ``author_id`` path, which
        ``_message_compute_author`` (line 2946) honours as given.

        The published ``message_type`` is the module constant, NEVER a value
        read back from the held row: the row does not store one precisely so
        that the type an untrusted author sent cannot survive the queue and
        surface at publication time.

        Approval is also the moment the held attachments become channel
        attachments again -- see ``_moderation_release_attachments`` for why
        that takes a step on each side of the post.
        """
        self.ensure_one()
        self._moderation_park_attachments(
            pending.sudo().attachment_ids.filtered(
                lambda attachment: attachment.res_model == HELD_ATTACHMENT_MODEL
            )
        )
        author_kwargs = {}
        if pending.guest_id:
            channel = (
                self.with_user(self.env.ref("base.public_user").sudo())
                .sudo()
                .with_context(guest=pending.guest_id.sudo())
            )
        else:
            channel = self.sudo()
            author_kwargs["author_id"] = pending.partner_id.id
        message = super(DiscussChannel, channel).message_post(
            body=pending.body or "",
            message_type=MODERATED_MESSAGE_TYPE,
            subtype_xmlid=MODERATED_MESSAGE_SUBTYPE,
            parent_id=pending.parent_id.id or False,
            attachment_ids=pending.attachment_ids.ids,
            **author_kwargs,
        )
        self._moderation_release_attachments(message)
        return message
