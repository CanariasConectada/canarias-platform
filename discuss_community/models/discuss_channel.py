# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models

# The other population that leaked into ``mail.channel_all_employees``: not
# a community member (only 2 of those exist), but 116 merchant accounts
# carrying a group named "Comerciante (migración)" that some pre-repo
# migration script granted directly, with no xmlid of its own -- confirmed
# by database inspection on 2026-08-20 (id 65 in prod, zero overlap with any
# admin/Settings group, and matching 116 of the channel's ~124 real members
# one for one). The 2026-08-20 production fix note gives that orphan group a
# stable xmlid via a one-time `ir_model_data` insert so this carve-out (and
# anything written after it) has something durable to `env.ref()`, instead
# of matching on a translatable name every future line of code would have to
# re-derive.
MIGRATED_MERCHANT_GROUP_XMLID = "discuss_community.group_migrated_merchant"


class DiscussChannel(models.Model):
    """Keep community members and migrated merchants out of staff channels.

    THE leak this closes: ``mail.channel_all_employees`` ("general") carries
    ``group_ids = [base.group_user]`` (``mail/data/discuss_channel_data.xml``),
    and mail auto-seats every user holding a channel's ``group_ids`` the
    moment the user is created or regrouped (``mail/models/discuss/
    res_users.py:13-28``). A community member IS ``base.group_user``, and so
    is a merchant with backend access, so without this carve-out both would
    be seated in the channel where the platform staff talks to itself --
    reading internal announcements, and each other's names in its member
    sidebar. That second half is not hypothetical: it shipped, at 116 real
    seats on a single channel before the 2026-08-20 fix.

    The carve-out is at the membership source, not a cleanup after the fact:
    ``_subscribe_users_automatically_get_members`` is the single method that
    decides who gets auto-seated (create, regroup and channel-edit all funnel
    through it), so filtering here covers every path with one rule. It does
    NOT retroactively unseat anyone already wrongly seated before this file
    existed or before a group's xmlid was assigned -- that is a one-time data
    cleanup, deliberately kept OUT of module code (see the 2026-08-20
    production fix note).

    A channel whose ``group_ids`` includes one of the carved-out groups
    itself is exempt from THAT group's carve-out: that is an administrator
    saying "auto-seat this population here", through the exact mechanism
    this override guards.
    """

    _inherit = "discuss.channel"

    def _carved_out_groups(self):
        """The groups whose holders must never be auto-seated, as a recordset."""
        xmlids = (
            "discuss_community.group_community_member",
            MIGRATED_MERCHANT_GROUP_XMLID,
        )
        groups = self.env["res.groups"]
        for xmlid in xmlids:
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                groups |= group
        return groups

    def _subscribe_users_automatically_get_members(self):
        members = super()._subscribe_users_automatically_get_members()
        carved_out_groups = self._carved_out_groups()
        if not carved_out_groups:
            return members
        for channel in self:
            exempt = channel.sudo().group_ids & carved_out_groups
            excluded_groups = carved_out_groups - exempt
            if not excluded_groups:
                continue
            excluded_partner_ids = set(
                excluded_groups.sudo().all_user_ids.partner_id.ids
            )
            if not excluded_partner_ids:
                continue
            members[channel.id] = [
                partner_id
                for partner_id in members[channel.id]
                if partner_id not in excluded_partner_ids
            ]
        return members
