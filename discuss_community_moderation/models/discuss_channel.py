# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models

from odoo.addons.mail.tools.discuss import Store

# The marker group of a registered community member. A community GUEST holds
# this group too (`_community_group_ids` hands both populations the same
# shape), which is why the guest flag is always tested FIRST in the hold
# decision below: a throwaway account must never ride the member probation
# out of moderation.
COMMUNITY_MEMBER_GROUP = "discuss_community.group_community_member"


class DiscussChannel(models.Model):
    """The community branch of the hold decision, plus the author's own view.

    The engine's `_moderation_hold` classifies exactly three personas --
    `mail.guest`, public and portal -- and ends on "internal users are never
    held". `discuss_community` made two populations of internal users that ARE
    the untrusted public: walk-in community guests (`is_community_guest`) and
    freshly registered community members (`group_community_member`). This
    override extends the classification to them without touching the engine's
    branches: super() runs first, and if super() says hold, we hold.

    The engine's discipline is inherited wholesale and on purpose:

    * `_moderation_hold` still TAKES NO ARGUMENT and READS NO CONTEXT. The
      community branch derives everything from ``env.user`` and
      ``_get_current_persona()``, both of which survive the ``sudo()`` the
      public routes post with (``sudo()`` does not change ``env.user``).
    * The held payload still goes through the engine's single funnel
      `_moderation_create_pending`: nothing is duplicated here, so every
      ceiling, sanitisation and notification of the engine applies to the
      community rows unchanged.
    * `_message_update_content` needs nothing from us: the engine routes its
      edit gate through `_moderation_hold`, so a below-threshold member
      editing a published message re-enters the queue exactly like a guest.

    KNOWN, INHERITED TRADE-OFF: text-bearing system notices (joined, left,
    renamed) posted AS a moderated persona go through the queue, because
    their text embeds a persona-controlled name -- the engine documents that
    choice for guests and portal users, and it applies identically to a
    below-threshold member self-joining a channel. Contentless notices are
    still dropped by the engine's `_moderation_is_contentless_notice`.
    """

    _inherit = "discuss.channel"

    # ------------------------------------------------------------------
    # The hold decision
    # ------------------------------------------------------------------

    def _moderation_hold(self):
        """Hold community guests, and community members still on probation.

        SUPER FIRST, AND ITS HOLD IS FINAL. The engine already answers for
        `mail.guest`, public and portal personas; this method only adds an
        answer where the engine said "internal, never held".
        """
        moderation = super()._moderation_hold()
        if moderation:
            return moderation
        return self._moderation_hold_community()

    def _moderation_hold_community(self):
        """The community-persona classification. Persona-only, like the engine.

        Reads nothing but ``env.user`` (session identity, not forgeable
        through ``post_data`` or the request context) and persistent data.
        Order of the branches, and why the order IS the decision:

        1. Personas the engine owns (`mail.guest`, public, portal) exit
           empty: super() already ruled on them, and ruling twice would let
           this branch contradict the engine's switches.
        2. A moderator of the channel is never held. Their approval is the
           decision this queue exists to collect; holding their own posts
           would have them approving themselves, which is the same as not
           being held, with extra rows.
        3. `is_community_guest` decides ALONE for guests, before the member
           group is looked at. Community guests hold `group_community_member`
           too, and letting them fall through to the probation branch would
           hand every throwaway account a path out of moderation (three
           approvals and the "anonymous" persona posts freely). Mirrors the
           engine's own guest branch: flag on -> held, flag off -> free, no
           fall-through.
        4. A community member is held until `_community_trust_reached` on
           THIS channel says otherwise.
        5. Internal users outside the community (staff, merchants,
           moderators of other channels) keep the engine's promise: never
           held.
        """
        self.ensure_one()
        moderation_model = self.env["discuss.channel.moderation"]
        user = self.env.user
        if user._is_public() or user._is_portal():
            return moderation_model
        partner, guest = self.env["res.partner"]._get_current_persona()
        if guest or not partner:
            return moderation_model
        moderation = moderation_model._get_for_channel(self)
        if not moderation:
            return moderation_model
        if moderation._is_moderator(user):
            return moderation_model
        # sudo: `is_community_guest` sits on res.users, which an internal
        # user cannot necessarily read for themselves beyond their own safe
        # fields; only the flag is read, nothing is handed back.
        if user.sudo().is_community_guest:
            return (
                moderation if moderation.moderate_community_guests else moderation_model
            )
        if user.has_group(COMMUNITY_MEMBER_GROUP):
            if not moderation.moderate_new_users:
                return moderation_model
            if self._community_trust_reached(moderation, partner):
                return moderation_model
            return moderation
        return moderation_model

    def _community_trust_reached(self, moderation, partner):
        """Whether ``partner`` has earned free posting on THIS channel.

        The measure is the count of the author's APPROVED
        `discuss.channel.pending.message` rows on this channel. An approved
        row is exactly "a moderator read this author's message here and
        published it", already stamped with moderator and date by the engine
        -- no extra bookkeeping is needed beyond counting.

        PER CHANNEL on purpose, consistent with everything else in the
        engine: the switch row, the pending quota and the moderator list are
        all scoped to the channel, and trust earned in the neighbourhood
        channel says nothing about how the same person behaves in another.

        Index-friendly by construction: the domain touches `channel_id`,
        `partner_id` and `state`, each an indexed column on the pending
        model, and `search_count` is bounded by ``limit=threshold`` so the
        query stops scanning the moment the answer is known.

        A threshold of zero or less disables probation entirely -- the field
        help documents that contract.
        """
        self.ensure_one()
        threshold = moderation.trust_threshold
        if threshold <= 0:
            return True
        # sudo: the author has no rights on the queue and must not get any;
        # only the COUNT of their own approved rows is read here. Same
        # bounded use of sudo as the engine's `_moderation_check_quota`.
        approved = (
            self.env["discuss.channel.pending.message"]
            .sudo()
            .search_count(
                [
                    ("channel_id", "=", self.id),
                    ("partner_id", "=", partner.id),
                    ("state", "=", "approved"),
                ],
                limit=threshold,
            )
        )
        return approved >= threshold

    # ------------------------------------------------------------------
    # The author's own pending rows, into the Discuss store
    # ------------------------------------------------------------------

    def _to_store_defaults(self, target):
        """Ship the caller's OWN held messages with the channel data.

        This is what makes the "Pending review" placeholder survive a reload:
        the Discuss client reads `cc_pending_messages` off the thread record
        the same way it reads any other channel field, and renders the
        author's held bodies at the bottom of the thread.
        """
        return super()._to_store_defaults(target) + [
            Store.Attr(
                "cc_pending_messages",
                lambda channel: channel._community_own_pending_store(),
            ),
        ]

    def _community_own_pending_store(self):
        """The CURRENT persona's pending rows on this channel. Only theirs.

        Same discipline, same shape, same reasoning as
        `website_pwa_chat._website_chat_pending`, which went through the
        adversarial rounds already:

        * Identity comes from `res.partner._get_current_persona()`, which
          returns an EMPTY partner for a public session -- so the partner
          branch is structurally unreachable from an anonymous request, and
          the shared `base.public_partner` (the author the engine writes on
          cookie-less holds) can never match a domain built here. A
          cookie-less visitor is shown nothing, not everybody's queue.
        * ``sudo()`` is unavoidable and bounded: the pending model is closed
          to everyone but moderators by design. The domain below IS the
          access policy of this read -- it names the persona explicitly.
        * Only ``state = 'pending'`` rows travel. Approved rows become real
          messages the client already renders; rejected rows are announced
          once, over the author's bus, and are not replayed on every reload.

        The early community check is a COST guard, not a security one: this
        attr is computed for every channel a session pulls into its store,
        and platform staff with hundreds of channels would otherwise pay one
        queue query per channel for a feature that cannot concern them.
        """
        self.ensure_one()
        partner, guest = self.env["res.partner"]._get_current_persona()
        if guest:
            author_domain = [("guest_id", "=", guest.id)]
        elif partner:
            user = self.env.user
            if not (
                user.sudo().is_community_guest or user.has_group(COMMUNITY_MEMBER_GROUP)
            ):
                return []
            author_domain = [("partner_id", "=", partner.id)]
        else:
            return []
        rows = (
            self.env["discuss.channel.pending.message"]
            .sudo()
            .search(
                [("channel_id", "=", self.id), ("state", "=", "pending")]
                + author_domain,
                order="id",
            )
        )
        return [row._community_pending_client_data() for row in rows]
