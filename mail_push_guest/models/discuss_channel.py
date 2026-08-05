# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models

# Message types core considers "somebody actually said something"
# (mail/models/discuss/discuss_channel.py:824-827). Kept in sync by hand: a
# guest must not be woken up by a tracking note or a system notification.
NOTIFIABLE_MESSAGE_TYPES = ("comment", "email", "email_outgoing", "whatsapp_message")

# Per-member notification settings that still mean "push me".
#
# Core resolves an unset (`False`) setting through
# `res.users.settings.channel_notifications`
# (mail/models/discuss/discuss_channel.py:886-898), which a guest does not
# have: applying that domain verbatim would drop every guest whose member row
# is untouched, i.e. all of them. So an unset guest is treated as "all".
#
# "mentions" is deliberately absent: a `mail.message` addresses partners
# (`partner_ids`), there is no guest-mention concept in core, so a guest asking
# for mentions only would be asking never to be woken up -- and that is exactly
# what excluding the value delivers. "no_notif" is honoured for the same
# reason it exists.
GUEST_NOTIFYING_SETTINGS = [False, "all"]


class DiscussChannel(models.Model):
    """Push to the guest members of a channel, not only to the partners.

    Recipient resolution in core is partner-shaped end to end:
    `_notify_get_recipients` searches members with `partner_id.active = True`
    (mail/models/discuss/discuss_channel.py:874-904), so a guest member never
    enters `recipients_data`; `_notify_thread_by_web_push` then turns that list
    into partner ids and `_web_push_get_partners_parameters` searches devices by
    `partner_id` (mail/models/mail_thread.py:3886-3909). A guest is not
    filtered out at the end -- it never gets in. Hence a parallel pass rather
    than a patched filter.
    """

    _inherit = "discuss.channel"

    def _notify_thread(self, message, msg_vals=False, **kwargs):
        """Cover the case where core never reaches the web push step at all.

        `_notify_thread` bails out with `if not recipients_data: return`
        (mail/models/mail_thread.py:3295-3296) BEFORE calling
        `_notify_thread_by_inbox`, `_notify_thread_by_email` and
        `_notify_thread_by_web_push`. Since `recipients_data` only ever holds
        partners, a channel whose only members are guests -- or whose only
        partner member is the author of this very message -- produces an empty
        list and returns early. Hooking `_notify_thread_by_web_push` alone
        would therefore work everywhere EXCEPT the case this module exists for.

        `not rdata` is exactly the early-return condition, which is what keeps
        this from double-sending: when core did get as far as the web push
        step, the override below already ran and this branch is skipped.
        """
        rdata = super()._notify_thread(message, msg_vals=msg_vals, **kwargs)
        if not rdata:
            self._web_push_notify_guest_members(message, msg_vals=msg_vals, **kwargs)
        return rdata

    def _notify_thread_by_web_push(
        self, message, recipients_data, msg_vals=False, **kwargs
    ):
        """Core first (partners), then the guests core cannot see.

        Order matters only for readability; the two passes touch disjoint sets
        of devices, since a device has exactly one persona.
        """
        super()._notify_thread_by_web_push(
            message, recipients_data, msg_vals=msg_vals, **kwargs
        )
        self._web_push_notify_guest_members(message, msg_vals=msg_vals, **kwargs)

    # ------------------------------------------------------------------
    # Guest pass
    # ------------------------------------------------------------------

    def _web_push_notify_guest_members(self, message, msg_vals=False, **kwargs):
        """Send one push per guest device of this channel.

        Mirrors the member filtering core applies to partners: the author is
        never notified, a muted member is never notified, and a member who
        turned notifications off is never notified.
        """
        self.ensure_one()
        msg_vals = msg_vals or {}
        message_type = (
            msg_vals["message_type"]
            if "message_type" in msg_vals
            else message.message_type
        )
        if message_type not in NOTIFIABLE_MESSAGE_TYPES:
            return
        devices, private_key, public_key = self._web_push_get_guests_parameters(
            self._web_push_get_guest_recipients(message, msg_vals=msg_vals).ids
        )
        if not devices:
            return
        payload = self._web_push_truncate_payload(
            self._web_push_guest_prepare_payload(
                message,
                msg_vals=msg_vals,
                force_record_name=kwargs.get("force_record_name"),
            )
        )
        # `payload=`, NEVER `payload_by_lang=`: the core sender indexes that
        # dict with `device.partner_id.lang`
        # (mail/models/mail_thread.py:3928 and :3947), which for a guest device
        # evaluates to False and raises KeyError. Delegating to the core sender
        # is also what keeps `MAX_DIRECT_PUSH` semantics honest -- under the
        # threshold it posts inline, over it it queues into `mail.push` and
        # triggers the cron, and the cron path never reads a partner either
        # (mail/models/mail_push.py:22-62).
        self._web_push_send_notification(
            devices, private_key, public_key, payload=payload
        )

    def _web_push_get_guest_recipients(self, message, msg_vals=False):
        """Guests of this channel that should be woken up by `message`.

        :returns: a `mail.guest` recordset (possibly empty)
        """
        self.ensure_one()
        msg_vals = msg_vals or {}
        author_guest_id = (
            msg_vals["author_guest_id"]
            if "author_guest_id" in msg_vals
            else message.author_guest_id.id
        )
        domain = [
            ("channel_id", "=", self.id),
            ("guest_id", "!=", False),
            ("mute_until_dt", "=", False),
            ("custom_notifications", "in", GUEST_NOTIFYING_SETTINGS),
        ]
        if author_guest_id:
            domain.append(("guest_id", "!=", author_guest_id))
        # sudo: discuss.channel.member - reading members of a channel whose
        # message we are already notifying; the poster may be a guest, who has
        # no read access to other members' rows.
        members = self.env["discuss.channel.member"].sudo().search(domain)
        return members.guest_id

    def _web_push_get_guests_parameters(self, guest_ids):
        """Guest counterpart of `_web_push_get_partners_parameters`.

        Same contract, same early exits, same tuple: devices (as sudo), private
        key, public key. It reads the VAPID parameters DIRECTLY instead of
        calling `mail.push.device.get_web_push_vapid_public_key()`, which
        unlinks every device on this database when the public key is missing
        (mail/models/mail_push_device.py:33-45).

        :param guest_ids: IDs of the `mail.guest` records
        """
        # sudo: mail.push.device is a base.group_system model
        # (mail/security/ir.model.access.csv:67-68).
        devices_su = self.env["mail.push.device"].sudo()
        if not guest_ids:
            return devices_su, None, None
        ir_params_su = self.env["ir.config_parameter"].sudo()
        vapid_private_key = ir_params_su.get_param("mail.web_push_vapid_private_key")
        vapid_public_key = ir_params_su.get_param("mail.web_push_vapid_public_key")
        if not vapid_private_key or not vapid_public_key:
            return devices_su, None, None
        return (
            devices_su.search([("guest_id", "in", guest_ids)]),
            vapid_private_key,
            vapid_public_key,
        )

    def _web_push_guest_prepare_payload(
        self, message, msg_vals=False, force_record_name=False
    ):
        """The notification a guest actually sees on their lock screen.

        Shape is a PRODUCT DECISION: author name plus the beginning of what
        they wrote -- "Maria in Guanarteme: does anybody know if..." -- and not
        just the channel name. A notification that says only "New message in
        Guanarteme" is one nobody acts on. The privacy cost is real and
        documented in the README: a phone shows this while locked.

        Everything except the title comes from core's builder, so the body
        stays html2plaintext'd, the attachment-only wording stays translated,
        and `_web_push_truncate_payload` still owns the 4 KB limit.
        """
        payload = self._notify_by_web_push_prepare_payload(
            message, msg_vals=msg_vals, force_record_name=force_record_name
        )
        payload["title"] = self._web_push_guest_title(
            message, msg_vals=msg_vals, force_record_name=force_record_name
        )
        return payload

    def _web_push_guest_title(self, message, msg_vals=False, force_record_name=False):
        """ "<author> in <channel>", or just the author in a 1-1 chat."""
        self.ensure_one()
        msg_vals = msg_vals or {}
        author_id = (
            msg_vals["author_id"] if "author_id" in msg_vals else message.author_id.id
        )
        author_guest_id = (
            msg_vals["author_guest_id"]
            if "author_guest_id" in msg_vals
            else message.author_guest_id.id
        )
        # sudo: a name read must not depend on who posted. The payload is built
        # once, in the poster's environment -- which for a guest is the public
        # user -- and then sent to every guest device of the channel.
        if author_id:
            author_name = self.env["res.partner"].sudo().browse(author_id).name
        elif author_guest_id:
            author_name = self.env["mail.guest"].sudo().browse(author_guest_id).name
        else:
            author_name = ""
        if self.channel_type == "chat":
            # In a 1-1 chat the channel name IS the other person: repeating it
            # would render "Maria in Maria".
            return author_name
        channel_name = force_record_name or message.record_name or self.sudo().name
        if not author_name:
            return channel_name or ""
        # The connector is translatable, but a single payload is sent to every
        # guest device, so it is rendered once in the environment's language --
        # the poster's. See ROADMAP.
        return self.env._(
            "%(author)s in %(channel)s", author=author_name, channel=channel_name
        )
