# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from collections import defaultdict

from odoo import api, fields, models

from odoo.addons.website_directory.models.website_directory_entry import ZONE_SELECTION

_logger = logging.getLogger(__name__)

# The zone that means "the whole platform". It is the first value of
# ``ZONE_SELECTION`` and the default of ``res.company.commercial_zone``, so it
# is also what everybody falls back to when no neighbourhood is known. Its
# channel is the general one: EVERYONE is a member of it, guests included as
# readers (they are never made members -- see ``_sync_zone_channels``).
GENERAL_ZONE = "canarias"

# One channel per zone, resolved by convention from the zone key. Keeping the
# xmlid derivable means a new zone needs a data row and nothing else: no map in
# Python to keep in sync with ``ZONE_SELECTION``, which is exactly the kind of
# second list ``res_company_zone`` already refused to carry.
CHANNEL_XMLID_TEMPLATE = "discuss_channel_zone.channel_%s"

# Users reconciled per transaction slice by the nightly cron. Large enough that
# a few thousand accounts are a handful of round trips, small enough that one
# batch is a bounded amount of work if it has to be retried.
CRON_BATCH_SIZE = 500


class ResUsers(models.Model):
    """Membership of the community channels, derived from the user's zone.

    The platform has four channels (one general, three neighbourhoods) and
    nobody joins them by hand: membership is a FUNCTION of who the user is.
    That function is ``_get_chat_zone``; ``_sync_zone_channels`` is the
    idempotent projection of that function onto ``discuss.channel.member``.
    """

    _inherit = "res.users"

    chat_zone = fields.Selection(
        selection=ZONE_SELECTION,
        string="Chat Zone",
        index=True,
        help="Neighbourhood channel this resident takes part in. Only used "
        "when the account is not linked to a business: a merchant's zone "
        "always comes from their company.",
    )

    @property
    def SELF_READABLE_FIELDS(self):
        # A resident has to be able to SEE the zone they picked on their own
        # profile, and a portal user may only read the fields listed here
        # (``_self_accessible_fields``, odoo/addons/base/models/res_users.py:176).
        return super().SELF_READABLE_FIELDS + ["chat_zone"]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        # "A resident with no company PICKS their zone" is the product
        # decision, and this list is the only thing that makes picking it
        # possible without handing the resident rights on ``res.users``.
        return super().SELF_WRITEABLE_FIELDS + ["chat_zone"]

    # ------------------------------------------------------------------
    # Zone resolution
    # ------------------------------------------------------------------

    def _get_chat_zone(self):
        """The zone whose channel this user belongs to, or False for a visitor.

        PRECEDENCE, highest first:

        1. **The company.** A merchant's zone is a property of their business,
           not of their taste, so a usable company always wins. "Usable" is the
           rule documented on ``res.company._get_own_company_for_directory``
           (``website_directory/models/res_company.py:192-216``): the platform's
           own company (``base.main_company``) is nobody's shop and an archived
           company is nobody's shop either, so both resolve to "no company".
        2. **The manual field.** ``chat_zone``, which an ordinary resident sets
           on their own profile. It is the fallback, never an override: a
           merchant cannot move their shop out of its neighbourhood by editing
           a dropdown.
        3. **The general zone.** Anyone left -- platform staff, a resident who
           never picked -- belongs to the platform-wide zone, i.e. to the
           general channel and to nothing else.

        Returns ``False`` for a public user: a visitor has no zone, and the
        general channel is open to them by group, not by membership.
        """
        self.ensure_one()
        return self._get_chat_zones()[self.id]

    def _get_chat_zones(self):
        """``{user_id: zone}`` for ``self``, in a bounded number of queries.

        The batch version exists because ``_sync_zone_channels`` runs over
        hundreds of accounts: resolving the company user by user would walk
        into ``res.company`` once per row. Everything that needs a company is
        answered from ONE ``sudo().search()``, which is also what makes the
        rule work for a portal user at all -- a portal session cannot walk a
        dotted path into ``res.company`` (the trap is documented at
        ``website_sale_marketplace/models/website.py:92-110``).

        ``search`` rather than ``browse`` on purpose: the default active test
        drops archived companies, which is half of the "usable company" rule
        this method has to honour.
        """
        users = self.sudo()
        company_model = self.env["res.company"].sudo()
        main_company = self.env.ref("base.main_company", raise_if_not_found=False)
        public_group = self.env.ref("base.group_public", raise_if_not_found=False)

        company_ids = {user.company_id.id for user in users if user.company_id}
        usable = (
            company_model.search([("id", "in", list(company_ids))])
            if company_ids
            else company_model.browse()
        )
        if main_company:
            usable -= main_company
        zone_by_company = {company.id: company.commercial_zone for company in usable}

        zones = {}
        for user in users:
            if public_group and public_group in user.all_group_ids:
                zones[user.id] = False
                continue
            raw = (
                zone_by_company.get(user.company_id.id)
                or user.chat_zone
                or GENERAL_ZONE
            )
            # Normalised, never trusted as-is: the migrated database still
            # holds ``lomo_los_frailes`` and friends, and the ORM only
            # validates a Selection on WRITE, so a legacy row reads back
            # verbatim. ``_normalise_zone`` is the single map for those
            # spellings (``res_company_zone/models/res_company.py:68-83``).
            zones[user.id] = company_model._normalise_zone(raw)
        return zones

    @api.model
    def _zone_channels(self):
        """``{zone: channel}`` for every zone that has a channel installed.

        Missing xmlids are skipped instead of raising: the sync runs from
        ``res.users.create``, which other modules call during their own
        installation, and a half-loaded registry must not break user creation.
        """
        channels = {}
        env = self.sudo().env
        for zone, _label in ZONE_SELECTION:
            channel = env.ref(CHANNEL_XMLID_TEMPLATE % zone, raise_if_not_found=False)
            if channel:
                channels[zone] = channel
        return channels

    @api.model
    def _zone_channel(self, zone):
        """The channel of ``zone``, legacy spellings included."""
        normalised = self.env["res.company"].sudo()._normalise_zone(zone)
        return self._zone_channels().get(
            normalised, self.env["discuss.channel"].browse()
        )

    # ------------------------------------------------------------------
    # Membership projection
    # ------------------------------------------------------------------

    def _zone_syncable_users(self):
        """The subset of ``self`` whose membership this module manages.

        Three exclusions, each for its own reason:

        * **Public users.** The visitor persona has no zone and must never
          become a member of anything -- the general channel is open to it by
          ``group_public_id = False``, which is a READ grant, not a seat.
        * **The superuser.** ``base.user_root`` is the account modules post as;
          it is not a resident and its presence in a community channel is
          noise.
        * **Archived users.** A deactivated account keeps whatever membership
          it had (history is not ours to rewrite) but is never re-seated.
        """
        users = self.filtered("active")
        # Defence in depth, and unreachable on purpose: today no ``self`` can
        # still contain the superuser at this point. ``base.user_root`` is
        # archived and core refuses to un-archive it -- "You cannot activate
        # the superuser" (odoo/addons/base/models/res_users.py:596-598) -- so
        # the ``filtered("active")`` above has already dropped it. Kept
        # because the exclusion is a RULE of this module -- the superuser is
        # not a resident -- and the line that enforces it must not depend on
        # another module's invariant staying true. It costs one ``env.ref``
        # and one recordset subtraction; deleting it makes the rule depend on
        # core never shipping an active root.
        root = self.env.ref("base.user_root", raise_if_not_found=False)
        if root:
            users -= root
        public_group = self.env.ref("base.group_public", raise_if_not_found=False)
        if public_group:
            users = users.filtered(lambda user: public_group not in user.all_group_ids)
        return users

    def _sync_zone_channels(self):
        """Make channel membership match ``_get_chat_zone`` for ``self``.

        Idempotent by construction: it computes the membership the users OUGHT
        to have, reads the membership they DO have in one query, and only
        touches the difference. Running it twice on an already-correct set
        performs no write at all, which is what makes it safe as a create/write
        trigger AND as a nightly reconciliation.

        Returns ``{"added": int, "removed": int}`` -- the drift it had to
        correct. The counters are the cron's log line and the assertion the
        idempotence test makes.

        Removal is a plain ``unlink`` on ``discuss.channel.member`` and NOT
        ``discuss.channel._action_unfollow``: the latter is one-channel,
        one-partner (``ensure_one``) with a bus round trip each time, so a
        reconciliation over hundreds of users would be N+1. Neither path posts
        anything on a ``channel_type == "channel"``
        (``mail/models/discuss/discuss_channel.py:578``), so leaving a zone
        stays as silent as joining one.

        Only ``partners=`` is ever passed to ``_add_members``: guests have no
        partner and are never seated by this module.
        """
        users = self.sudo()._zone_syncable_users()
        counters = {"added": 0, "removed": 0}
        if not users:
            return counters

        channels = self._zone_channels()
        general = channels.get(GENERAL_ZONE)
        if not general:
            _logger.warning(
                "discuss_channel_zone: general channel %s is missing, "
                "membership sync skipped for %s users",
                CHANNEL_XMLID_TEMPLATE % GENERAL_ZONE,
                len(users),
            )
            return counters

        zones = users._get_chat_zones()
        wanted = defaultdict(set)  # {channel: {partner_id}}
        for user in users:
            partner_id = user.partner_id.id
            wanted[general].add(partner_id)
            zone_channel = channels.get(zones.get(user.id))
            if zone_channel and zone_channel != general:
                wanted[zone_channel].add(partner_id)

        # Every managed channel is scanned, not only the wanted ones: a user
        # who LEFT a zone has a membership on a channel that no longer appears
        # in ``wanted``, and that row is precisely what has to go.
        managed = self.env["discuss.channel"].browse()
        for channel in channels.values():
            managed |= channel
        member_model = self.env["discuss.channel.member"].sudo()
        existing = member_model.search(
            [
                ("channel_id", "in", managed.ids),
                ("partner_id", "in", users.partner_id.ids),
            ]
        )
        existing_by_channel = defaultdict(set)
        for member in existing:
            existing_by_channel[member.channel_id].add(member.partner_id.id)

        partner_model = self.env["res.partner"].sudo()
        for channel in managed:
            missing = wanted[channel] - existing_by_channel[channel]
            if not missing:
                continue
            channel.sudo()._add_members(
                partners=partner_model.browse(sorted(missing)),
                # Redundant on a "channel" (core posts no join notice for that
                # type) and stated anyway: this module must stay silent even if
                # that ever changes.
                post_joined_message=False,
            )
            counters["added"] += len(missing)

        stale = existing.filtered(
            lambda member: member.partner_id.id not in wanted[member.channel_id]
        )
        counters["removed"] = len(stale)
        stale.unlink()
        return counters

    # ------------------------------------------------------------------
    # Triggers
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """A new account is seated the moment it exists.

        Without this a resident would see an empty Discuss until the nightly
        cron ran, which for a community platform means "the chat is broken".
        """
        users = super().create(vals_list)
        users._sync_zone_channels()
        return users

    def write(self, vals):
        """Re-seat when the INPUTS of ``_get_chat_zone`` change, and only then.

        ``company_id`` and ``chat_zone`` are the two fields the zone is derived
        from on this model. Every other write -- ``login_date`` on each login,
        a signature, a language -- must not cost a membership scan.
        """
        result = super().write(vals)
        if {"company_id", "chat_zone"} & vals.keys():
            self._sync_zone_channels()
        return result

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------

    @api.model
    def _cron_sync_zone_channels(self, batch_size=CRON_BATCH_SIZE):
        """Nightly reconciliation of every active account.

        The triggers above cover the changes that go through the ORM. This
        covers everything else: a SQL migration, a restored backup, a channel
        somebody left by hand from Discuss, a user created while the module was
        uninstalled. The log line reports the DRIFT (memberships added and
        removed), not the number of users looked at -- a healthy platform
        prints zeros, and a non-zero line is a fact worth reading.
        """
        users = self.sudo().search([])
        totals = {"added": 0, "removed": 0}
        for start in range(0, len(users), batch_size):
            counters = users[start : start + batch_size]._sync_zone_channels()
            totals["added"] += counters["added"]
            totals["removed"] += counters["removed"]
        _logger.info(
            "discuss_channel_zone: reconciled %s users, drift %s added / %s removed",
            len(users),
            totals["added"],
            totals["removed"],
        )
        return totals
