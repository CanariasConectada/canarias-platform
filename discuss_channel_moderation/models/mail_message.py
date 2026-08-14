# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import unicodedata

from odoo import _, models
from odoo.exceptions import UserError

# A reaction is a grapheme, not a sentence. The ceiling is in CODEPOINTS, and
# it has to leave room for the long legitimate ones: a family emoji is 7
# codepoints (four faces joined by three ZWJs), a flag is 2, a skin-toned
# thumb is 2, a keycap is 3.
MAX_REACTION_LENGTH = 16

# Categories a codepoint of an emoji sequence can legitimately have:
# So  symbol/other      the emoji themselves, regional indicators
# Sk  symbol/modifier   skin tone modifiers
# Cf  format            ZERO WIDTH JOINER, used to build compound emoji
# Mn  mark/non-spacing  VARIATION SELECTOR-16
# Me  mark/enclosing    COMBINING ENCLOSING KEYCAP
# Nd  decimal digit     the 0-9 base of a keycap sequence
ALLOWED_REACTION_CATEGORIES = frozenset({"So", "Sk", "Cf", "Mn", "Me", "Nd"})

# The two keycap bases that are NOT digits, and the mark that turns them into
# an emoji. Listed one by one instead of opening their whole Unicode category
# (Po, "punctuation/other"), which would have let a reaction be a line of
# punctuation with an emoji hidden in it.
KEYCAP_BASES = frozenset("#*")
KEYCAP_MARK = "⃣"  # COMBINING ENCLOSING KEYCAP

# At least one codepoint must come from one of these, so a string of joiners,
# digits or invisible marks is not accepted as "an emoji". ``Me`` is in the
# list because a combining enclosing keycap only ever occurs in a keycap emoji.
REQUIRED_REACTION_CATEGORIES = frozenset({"So", "Sk", "Me"})


class MailMessage(models.Model):
    """Two things a message carries that are NOT its body: reactions, previews.

    Reactions are guarded here. Link previews are decided here
    (``_moderation_previews_blocked``) and enforced in ``mail_link_preview.py``
    and ``mail_message_link_preview.py``.

    Reactions are free text server-side. On a moderated channel they are not.

    THE bypass this closes: ``/mail/message/reaction`` is ``auth="public"`` and
    core validates nothing about ``content`` -- ``_message_reaction``
    (``mail/models/mail_message.py:1003``) writes it into a plain
    ``Char`` (``mail/models/mail_message_reaction.py:15``) and
    ``_reaction_group_to_store`` serves it back to everyone reading the
    message. The validation posted ``"REACTION-ARBITRARY-TEXT"`` and then a
    5000-character ``content``, both stored at full length and both served to a
    third party. Emoji validation is client-side only, which is to say it is
    not validation.

    The guard is a SHAPE check, not a list. An allow-list of emoji would need
    updating with every Unicode release and would reject legitimate compound
    sequences the day they ship; asking "is every codepoint one an emoji
    sequence is made of, and is at least one of them an actual symbol?" is
    cheap, has no table to maintain, and is exactly the property the field is
    supposed to hold.

    Scope is the same persona question as everywhere else: it applies to an
    untrusted persona on a moderated channel. An internal user keeps core's
    behaviour, and so does every unmoderated channel -- this module moderates
    the channels it was pointed at, and nothing else.
    """

    _inherit = "mail.message"

    def _message_reaction(self, content, action, partner, guest, store=None):
        self._moderation_check_reaction(content, action)
        return super()._message_reaction(content, action, partner, guest, store)

    def _moderation_previews_blocked(self):
        """Whether link previews are forbidden for this message.

        Answers a CHANNEL question, not a persona one, and that is deliberate --
        see ``mail_link_preview.py`` for the three reasons. Lives on
        ``mail.message`` because both preview models reach the decision from a
        message and neither should have to know how a channel is moderated.
        """
        self.ensure_one()
        # sudo: ``mail.message`` access is code-driven and document-scoped, and
        # the caller here is an untrusted persona; only the thread coordinates
        # of the message are read.
        message = self.sudo()
        if message.model != "discuss.channel":
            return False
        channel = self.env["discuss.channel"].sudo().browse(message.res_id).exists()
        if not channel:
            return False
        return bool(self.env["discuss.channel.moderation"]._get_for_channel(channel))

    def _moderation_check_reaction(self, content, action):
        """Refuse a non-emoji reaction from an untrusted persona.

        Only ``add`` is checked. Removing a reaction publishes nothing -- and a
        guard on ``remove`` would strand whatever was stored before this fix
        shipped, since its author could no longer take it back.
        """
        self.ensure_one()
        if action != "add" or self.model != "discuss.channel":
            return
        # sudo: the reacting persona has no rights on the moderation
        # configuration; only the hold decision is read from it.
        channel = self.env["discuss.channel"].sudo().browse(self.res_id).exists()
        if not channel or not channel._moderation_hold():
            return
        if not self._moderation_is_emoji(content):
            raise UserError(_("A reaction must be a single emoji."))

    @staticmethod
    def _moderation_is_emoji(content):
        """Whether ``content`` has the shape of one emoji sequence.

        Length is counted in CODEPOINTS, which is what a compound emoji is made
        of: ``len("👨‍👩‍👧‍👦")`` is 7, not 1 and not 25.
        """
        if not content or len(content) > MAX_REACTION_LENGTH:
            return False
        bases = sum(char in KEYCAP_BASES for char in content)
        if bases and (bases > 1 or KEYCAP_MARK not in content):
            # ``#`` and ``*`` are only ever emoji as the base of ONE keycap.
            return False
        categories = {
            unicodedata.category(char) for char in content if char not in KEYCAP_BASES
        }
        return categories <= ALLOWED_REACTION_CATEGORIES and bool(
            categories & REQUIRED_REACTION_CATEGORIES
        )
