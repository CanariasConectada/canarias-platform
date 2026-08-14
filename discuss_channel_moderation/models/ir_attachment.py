# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, models
from odoo.exceptions import AccessError

from .discuss_channel import DRAFT_ATTACHMENT_MODEL, HELD_ATTACHMENT_MODEL

# What a reader of a published attachment actually receives: the bytes, the
# label above them, and the picture shown instead of them. Changing any of these
# on an approved file publishes NEW content under an OLD decision, which is the
# round-two "approve once, then rewrite" bypass wearing a different field name.
#
# ``res_model``/``res_id`` are deliberately NOT here. Moving a file out of the
# channel UNPUBLISHES it, and that is what ``_moderation_park_attachments`` does
# on the author's own behalf when they edit or withdraw their message.
PUBLISHED_CONTENT_FIELDS = frozenset(
    {
        "checksum",
        "datas",
        "db_datas",
        "index_content",
        "mimetype",
        "name",
        "raw",
        "store_fname",
        "thumbnail",
        "type",
        "url",
    }
)


class IrAttachment(models.Model):
    """An untrusted upload never becomes a channel attachment on its own.

    THE bypass this closes, and it needed neither a message nor an approval:
    ``/mail/attachment/upload`` is ``auth="public"`` and writes an
    ``ir.attachment`` with ``res_model='discuss.channel'`` straight away
    (``mail/controllers/attachment.py:55-72``), while
    ``/discuss/channel/attachments`` -- also ``auth="public"`` -- searches on
    ``res_model``/``res_id`` alone and returns everything it finds through
    ``Store``, ``raw_access_token`` included
    (``mail/models/ir_attachment.py:100``). The validation had a guest upload a
    file to a MODERATED channel, an anonymous visitor list it, and
    ``/web/content/<id>?access_token=...`` serve the bytes with HTTP 200. The
    file was linked to no message and to no held row: uploading was enough.

    WHY THE GATE IS HERE and not on the upload route. The route is one door;
    ``create`` is the wall. Filtering what ``/discuss/channel/attachments``
    returns would have been smaller code, but it would leave the file sitting
    on the channel and make correctness the duty of every present and future
    reader -- the next route, the next widget, the next module. Refusing to
    write the link in the first place makes that route, and every other reader
    of channel attachments, correct because there is nothing to find.

    The replacement shape is core's OWN placeholder for a not-yet-posted
    upload, the one the real Discuss composer already asks for whenever it
    sends ``is_pending`` (``mail/controllers/attachment.py:61-69``,
    ``mail/static/src/core/common/attachment_upload_service.js`` sets it from
    the composer). So the deferred upload is not an invented state: it is the
    state uploads normally pass through, and the uploader keeps working with
    it through the ownership token the route hands them back. If the message is
    then held, ``_moderation_hold_attachments`` re-parents the file onto the
    held row, where the moderator -- and only the moderator -- can open it.

    ``create`` is only the first of three gates on this model, because a file
    has a life after it is uploaded and the author keeps the ownership token
    for all of it:

    - ``unlink`` / ``write`` on a HELD file -- the moderator's evidence, which
      its author was able to destroy. See ``_moderation_check_evidence``.
    - ``write`` on a PUBLISHED file's content -- the approved bytes, the label
      and the thumbnail, which its author was able to swap after approval. See
      ``_moderation_check_published_content``.
    """

    _inherit = "ir.attachment"

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._moderation_defer_vals(v) for v in vals_list])

    def write(self, vals):
        self._moderation_check_evidence()
        self._moderation_check_published_content(vals)
        return super().write(vals)

    def unlink(self):
        self._moderation_check_evidence()
        return super().unlink()

    def _moderation_check_published_content(self, vals):
        """An approved file cannot be swapped for another one afterwards.

        FOUND BY ENUMERATING THE PUBLIC ROUTES, not by a report, and it is the
        round-two bypass again with a different verb.
        ``/mail/attachment/update_thumbnail``
        (``mail/controllers/attachment.py:129-152``) is ``auth="public"`` and
        accepts either write access OR the ownership token -- the token the
        upload route handed the author, which they keep forever. So after ONE
        approval the author could write an arbitrary image into ``thumbnail``,
        and every reader of the channel is served it through
        ``has_thumbnail`` + ``thumbnail_access_token``
        (``mail/models/ir_attachment.py:97-103``). Exactly the "approve once,
        then publish anything" shape ``_message_update_content`` closes for
        bodies.

        UNLINK IS NOT GUARDED HERE, on purpose. Removing published content
        publishes nothing, and the module already refuses to treat "delete my
        own message" as a moderation task; making "delete my own file" one
        would be the same mistake.

        The persona question is asked through ``_moderation_hold``, so a
        channel that does not moderate this persona keeps core's behaviour
        untouched.
        """
        if not PUBLISHED_CONTENT_FIELDS.intersection(vals):
            return
        user = self.env.user
        if not user or user._is_internal():
            return
        # sudo: the author has no rights on the moderation configuration; only
        # where each file currently hangs, and whether that channel holds them.
        for attachment in self.sudo():
            if attachment.res_model != "discuss.channel":
                continue
            channel = (
                self.env["discuss.channel"].sudo().browse(attachment.res_id).exists()
            )
            if channel and channel._moderation_hold():
                raise AccessError(
                    _(
                        "This file was published after review and can no longer "
                        "be changed. Post it again to have the new version "
                        "reviewed."
                    )
                )

    def _moderation_check_evidence(self):
        """An untrusted persona cannot touch the file of a message they posted.

        THE defect this closes: ``/mail/attachment/delete``
        (``mail/controllers/attachment.py:88-98``) is ``auth="public"`` and its
        only check is ``_has_attachments_ownership``, which the UPLOADER
        satisfies for as long as they keep the ownership token the upload route
        handed them (``mail/models/ir_attachment.py:22-35``). Re-parenting the
        file onto the held row does not revoke that token. The validation had a
        guest delete the attachment of their OWN held message: the row was gone
        and the moderator was left looking at a pending message whose file list
        was empty -- asked to decide on evidence the author had just destroyed.

        WHY BOTH ``write`` AND ``unlink``. Deleting is the observed attack;
        re-parenting is the same attack with a different verb. A ``write`` that
        moved ``res_model`` back to ``discuss.channel`` would publish the file
        through ``/discuss/channel/attachments`` without any approval, and one
        that replaced ``raw`` would swap the reviewed bytes for others. The
        guard is on the RECORD's current state, so it covers every field.

        WHY THE TEST IS "IS THE CALLER INTERNAL" and not ``_moderation_hold()``.
        The hold reads the moderation configuration, which can be archived or
        have its ``moderate_guests`` flag flipped after the file was held --
        which would silently re-open the deletion on rows already in the queue.
        Only an internal user (a moderator, or the module's own publication
        path running as one) ever has business touching held evidence, so that
        is the whole rule and it cannot be turned off by editing configuration.

        DECIDED rows keep their files too. This model's rows are history: it
        never deletes a decided one, and the attachment of a rejected message is
        the record of what was rejected.
        """
        user = self.env.user
        if not user or user._is_internal():
            # ``not user`` is the environment with no ``uid`` at all, which some
            # low-level tooling builds; it is never an untrusted visitor.
            return
        # sudo: the persona reaching this has no rights on the attachment nor on
        # the queue; only the parenting of the rows they are touching is read.
        held = self.sudo().filtered(
            lambda attachment: attachment.res_model == HELD_ATTACHMENT_MODEL
        )
        if not held:
            return
        raise AccessError(
            _(
                "This file is attached to a message waiting for moderation and "
                "cannot be changed or removed."
            )
        )

    @api.model
    def _moderation_defer_vals(self, vals):
        """Rewrite an untrusted upload aimed at a moderated channel.

        Reads only ``res_model``/``res_id`` and the session identity: as
        everywhere else in this module, the persona decides and the payload
        does not. Anything else -- a trusted author, an unmoderated channel, an
        attachment aimed at another model -- is returned untouched, so the
        override is invisible outside the case it exists for.
        """
        if vals.get("res_model") != "discuss.channel" or vals.get("res_field"):
            # ``res_field`` means the row IS a field's storage (the channel
            # avatar, say), not content posted to the channel. Moving it would
            # not hide anything, it would break the field.
            return vals
        try:
            res_id = int(vals.get("res_id") or 0)
        except (TypeError, ValueError):
            return vals
        if not res_id:
            return vals
        # sudo: the uploader is by definition an untrusted persona with no
        # rights on the moderation configuration, and must not be granted any.
        channel = self.env["discuss.channel"].sudo().browse(res_id).exists()
        if not channel or not channel._moderation_hold():
            return vals
        return {**vals, "res_model": DRAFT_ATTACHMENT_MODEL, "res_id": 0}
