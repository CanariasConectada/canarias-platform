# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models


class MailLinkPreview(models.Model):
    """No link preview is ever generated for a message on a moderated channel.

    THE bypass this closes. ``/mail/link_preview``
    (``mail/controllers/link_preview.py:9``) is ``auth="public"`` and its only
    guard is ``message.is_current_user_or_guest_author`` -- and after ONE
    approval the guest IS the author. The validation ran it end to end: a guest
    posted an innocent link, a moderator read the body and approved it, the
    attacker then flipped the ``og:`` tags on their own page, the guest called
    the route, and a ``mail.link.preview`` row appeared carrying
    attacker-controlled ``og_title``, ``og_description``, ``og_image`` and
    ``og_site_name``. ``/discuss/channel/messages`` serves all of it to
    anonymous readers (``mail/models/mail_message.py:1098``,
    ``message_link_preview_ids`` is in ``_to_store_defaults``). Zero pending
    rows were created: the moderator never saw, and could never have seen, what
    was published under their approval.

    WHY THE RULE IS PER CHANNEL AND NOT PER PERSONA -- this is the one place the
    module deliberately does NOT ask the persona question, and the reason
    matters more than the rule.

    1. A PREVIEW IS NOT REVIEWABLE CONTENT. It is a promise to render whatever
       a third-party server says, later. ``og_image`` is stored as a URL
       (``mail/models/mail_link_preview.py:26``) and re-fetched by EVERY
       reader's browser on EVERY view, so it is a permanently live, never
       reviewed image slot and an IP beacon on every reader. No approval can
       bind content that the publisher can change after the approval. Holding a
       preview in the queue would therefore be moderation theatre: the
       moderator would approve bytes that are guaranteed to be stale.
    2. GATING ON THE TRIGGERING PERSONA WOULD NOT EVEN WORK. ``mail.link.preview``
       is keyed by a UNIQUE index on ``source_url``
       (``mail/models/mail_link_preview.py:35``), i.e. the OG payload is cached
       globally and reused for every message mentioning that URL. A rule that
       looked at who CALLED the route would let an admin (the route's other
       accepted caller) or a message on any other channel populate the cache
       with the same attacker-controlled row, which is then served on the
       moderated channel. Gating on the caller is exactly the class of mistake
       the earlier rounds were: the payload, or the caller, steers the gate.
    3. IT ALSO CLOSES THE SSRF. ``get_link_preview_from_url``
       (``mail/tools/link_preview.py:10-37``) does a plain ``requests.get``
       with ``allow_redirects=True`` and no host or IP filtering, on a URL an
       untrusted persona chose. Refusing to start the fetch for a moderated
       channel means no untrusted persona can make the server reach an address
       of their choosing through this route.

    WHAT IS LOST: on a moderated channel nobody -- moderators and internal
    users included -- gets a rich link card. The link itself still renders as an
    ordinary clickable anchor in the message body, so no information disappears;
    only the decoration does. That is the price of being able to say "a human
    approved everything a reader is served on this channel" and mean it.

    A HELD message needs no rule of its own: it is not a ``mail.message`` at
    all, so ``/mail/link_preview`` cannot find it. Generating a preview for a
    pending row would leak both the existence and the content of a message
    nobody has decided on yet, which is why the held payload deliberately never
    becomes a message before approval.
    """

    _inherit = "mail.link.preview"

    @api.model
    def _create_from_message_and_notify(self, message, request_url=None):
        """Stop BEFORE the outgoing HTTP request, not after it.

        The override sits here rather than only on
        ``mail.message.link.preview.create`` because this is the method that
        performs the fetch. Returning early is what makes the SSRF unreachable;
        the ``create`` guard next door is the wall behind it.
        """
        if message._moderation_previews_blocked():
            return None
        return super()._create_from_message_and_notify(message, request_url=request_url)
