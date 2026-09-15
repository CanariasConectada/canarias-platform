# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models

GROUP_XMLID = "zca_manager_group.group_zca_manager"


class ResUsers(models.Model):
    _inherit = "res.users"

    def _get_chat_zones(self):
        """A zone manager belongs to the chat channel of their zone.

        ``discuss_channel_zone`` derives the zone from the company's
        ``commercial_zone``, and a zone company carries "canarias" there
        (a zone is not a shop of a neighbourhood), so the manager would be
        seated in the general channel only. Their company IS the zone:
        ``zone_company_key`` says which one.

        Members of the group only. The residents who signed up on a zone
        website carry the zone company as well, and where they sit is that
        module's decision, not this one's.
        """
        zones = super()._get_chat_zones()
        group = self.env.ref(GROUP_XMLID, raise_if_not_found=False)
        if not group:
            return zones
        for user in self.sudo():
            key = user.company_id.zone_company_key
            # ``False`` is the public user: never seated anywhere.
            if key and zones.get(user.id) and group in user.all_group_ids:
                zones[user.id] = key
        return zones

    def write(self, vals):
        """Ticking the group changes the answer above: re-seat right away.

        ``discuss_channel_zone`` only re-syncs on ``company_id`` and
        ``chat_zone``; without this the manager would wait for the nightly
        reconciliation to see their zone channel.
        """
        result = super().write(vals)
        if "group_ids" in vals:
            self._sync_zone_channels()
        return result
