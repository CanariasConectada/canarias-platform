# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models

# Writes on a group that change who holds it, directly or by implication.
MEMBERSHIP_FIELDS = {"user_ids", "all_user_ids", "implied_ids", "implied_by_ids"}


class ResGroups(models.Model):
    """Refresh the cached record-rule domains on group-side changes.

    The community record rules branch on ``user.is_community_member``, i.e.
    on the user's groups, and ``ir.rule._compute_domain`` is ormcached per
    uid. Core clears that cache when ``res.users.group_ids`` is written, but a
    change made FROM THE GROUP (adding a user on the group form, or changing
    what a group implies) only clears the ``groups`` cache, so the old rule
    domains would keep applying until the next restart.
    """

    _inherit = "res.groups"

    def write(self, vals):
        result = super().write(vals)
        if MEMBERSHIP_FIELDS & vals.keys():
            self.env.registry.clear_cache()
        return result
