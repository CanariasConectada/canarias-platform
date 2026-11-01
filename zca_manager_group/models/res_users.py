# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, models
from odoo.exceptions import ValidationError

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

    @api.constrains("company_id", "company_ids", "group_ids")
    def _check_zca_manager_zone(self):
        """One manager, one zone, and the zone is the session company.

        Every rule of the profile reads ``company_ids``: a manager allowed
        into two companies would read two zones, and one whose company is
        a shop rather than a zone would manage nothing (or, worse, the
        shop). Refused at the source rather than trusted to the form.
        """
        group = self.env.ref(GROUP_XMLID, raise_if_not_found=False)
        if not group:
            return
        for user in self.sudo():
            if group not in user.group_ids:
                continue
            if len(user.company_ids) != 1 or user.company_id != user.company_ids:
                raise ValidationError(
                    _(
                        "%s is a ZCA Manager: the only allowed company must be "
                        "the zone company.",
                        user.name,
                    )
                )
            if not user.company_id.zone_company_key:
                raise ValidationError(
                    _(
                        "%(user)s is a ZCA Manager, but %(company)s is not a zone "
                        "company.",
                        user=user.name,
                        company=user.company_id.name,
                    )
                )

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
