# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class DiscussChannel(models.Model):
    """Keep community members out of the staff's auto-subscribed channels.

    THE leak this closes: ``mail.channel_all_employees`` ("general") carries
    ``group_ids = [base.group_user]`` (``mail/data/discuss_channel_data.xml``),
    and mail auto-seats every user holding a channel's ``group_ids`` the
    moment the user is created or regrouped (``mail/models/discuss/
    res_users.py:13-28``). A community member IS ``base.group_user``, so
    without this carve-out every walk-in guest would be seated in the
    channel where the platform staff talks to itself -- reading internal
    announcements and pushing bus traffic to the whole team.

    The carve-out is at the membership source, not a cleanup after the fact:
    ``_subscribe_users_automatically_get_members`` is the single method that
    decides who gets auto-seated (create, regroup and channel-edit all funnel
    through it), so filtering here covers every path with one rule.

    A channel whose ``group_ids`` includes the community group itself is
    exempt: that is an administrator saying "auto-seat community members
    here", and saying it through the exact mechanism this override guards.
    """

    _inherit = "discuss.channel"

    def _subscribe_users_automatically_get_members(self):
        members = super()._subscribe_users_automatically_get_members()
        community_group = self.env.ref(
            "discuss_community.group_community_member", raise_if_not_found=False
        )
        if not community_group:
            return members
        community_partner_ids = set(community_group.sudo().all_user_ids.partner_id.ids)
        if not community_partner_ids:
            return members
        for channel in self:
            if community_group in channel.sudo().group_ids:
                continue
            members[channel.id] = [
                partner_id
                for partner_id in members[channel.id]
                if partner_id not in community_partner_ids
            ]
        return members
