# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re

from odoo import _, api, models
from odoo.exceptions import UserError

# A byline, not a message. Core allows 512 characters
# (``mail/models/discuss/mail_guest.py:87-95``), which is a paragraph pretending
# to be a name.
MAX_GUEST_NAME_LENGTH = 64

# Anything that looks like a tag, plus any leftover angle bracket, so nothing
# can BECOME markup later in a renderer that trusts the field.
MARKUP_RE = re.compile(r"<[^>]*>")


class MailGuest(models.Model):
    """A guest's display name is content served to third parties too.

    THE gap this closes: ``/mail/guest/update_name`` is ``auth="public"`` and
    ``_update_name`` only checks that the name is non-empty and under 512
    characters. The validation set a guest's name to
    ``GUESTNAME-<b>spam</b>``, and it was rendered next to their approved
    message and served to everyone reading the channel. Moderating the body
    while the byline stays free text is half a control: the same persona, the
    same readers, a different field.

    SANITISED, NOT HELD. Holding a rename would mean a second queue with its
    own state machine, its own notifications and its own approval UI, for a
    field with no body, no attachments and no thread -- a lot of surface for
    a byline. It would also race the ordinary flow, since a guest can rename
    themselves before ever touching a moderated channel and the pending name
    would have to be resolved somewhere. Stripping markup and capping the
    length removes what made the name abusable and costs one function.

    APPLIED TO EVERY GUEST RENAME, not only to guests of moderated channels.
    A guest IS the untrusted persona this module is about, the name follows
    them into every channel they visit, and the rename can legitimately happen
    before they join anything -- so scoping the guard to "guests of a moderated
    channel" would buy nothing except an ordering trick (rename first, join
    after) to get around it.

    AND TO EVERY GUEST CREATION, which is a separate door the first version
    missed while claiming to cover "every guest". ``_update_name`` is only the
    RENAME path; a guest is BORN in ``_get_or_create_guest``
    (``mail/models/discuss/mail_guest.py:70-81``), which writes ``guest_name``
    straight through. In plain ``mail`` that name is a constant (``"Guest"``,
    or an email out of a server-signed token, ``public_page.py:100-104``), so
    nothing attacker-controlled reaches it -- but ``im_livechat``, which this
    platform will install, passes the visitor's own typed name to that same
    method. Guarding ``create`` rather than ``_get_or_create_guest`` follows
    the module's usual shape: the route is one door, ``create`` is the wall.
    """

    _inherit = "mail.guest"

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._moderation_clean_vals(v) for v in vals_list])

    @api.model
    def _moderation_clean_vals(self, vals):
        """Clean an incoming name, and ONLY when there is one to clean.

        An absent or empty ``name`` is left exactly as it came so the ORM's own
        required-field error is what the caller sees; raising our "cannot be
        empty" here would replace a precise message with a vaguer one for a
        case that has nothing to do with abuse.
        """
        if not vals.get("name"):
            return vals
        return {**vals, "name": self._moderation_clean_name(vals["name"])}

    def _update_name(self, name):
        return super()._update_name(self._moderation_clean_name(name))

    def _moderation_clean_name(self, name):
        """Plain, printable, short. Truncated rather than refused.

        A name is cosmetic: refusing the whole rename because it is two
        characters too long would be a worse experience than trimming it, and
        the abuse being prevented is the length itself, not the intent. Markup
        is a different matter and is removed outright -- there is no such thing
        as a name that legitimately contains a tag.

        Emptiness is NOT handled here: core already refuses an empty name, and
        keeping that single error message means a name made only of markup
        fails exactly like a name made only of spaces.
        """
        cleaned = MARKUP_RE.sub("", name or "")
        cleaned = cleaned.replace("<", "").replace(">", "")
        # Collapse every run of whitespace (newlines and tabs included) and
        # drop non-printables, so the byline cannot be padded into a banner.
        cleaned = " ".join(
            "".join(
                char for char in cleaned if char.isprintable() or char.isspace()
            ).split()
        )
        if len(cleaned) > MAX_GUEST_NAME_LENGTH:
            cleaned = cleaned[:MAX_GUEST_NAME_LENGTH].strip()
        if not cleaned:
            # Core's own message, raised here because after stripping there is
            # nothing left to hand it.
            raise UserError(_("Guest's name cannot be empty."))
        return cleaned
