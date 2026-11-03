# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import Command, api, models

from .res_company import SKIP_CONTEXT


class ResUsers(models.Model):
    _inherit = "res.users"

    def _zone_company_holders(self):
        """The users a zone company may legitimately stay on.

        Two populations, and only two:

        * the staff OF a zone -- their own company IS the zone company, so
          taking it away would leave them logged into a company they are not
          allowed into, which core rejects outright;
        * the platform administrators, who hold every company by design.

        ``base.group_multi_company`` is deliberately NOT an exemption. It is
        held by the merchants themselves, which is exactly the population this
        guard exists to protect: exempting it would make the guard a no-op.
        """
        zones = self.env["res.company"]._zone_companies()
        system = self.env.ref("base.group_system", raise_if_not_found=False)
        keep = self.browse()
        for user in self.sudo():
            if user.company_id in zones or (system and system in user.all_group_ids):
                keep |= user
        return self.browse(keep.ids)

    def _drop_zone_companies(self):
        """Take the zone companies out of these users' allowed companies.

        A merchant's *products* carry their zone company -- that is what puts
        them in the zone shop. Their *user* must not: ``company_ids`` is what
        every multi-company record rule reads, so a zone company there does not
        mean "my catalogue is in the zone shop", it means "I may read and write
        everything the zone owns" -- which is every other merchant of the
        neighbourhood. Guanarteme alone owns 1186 products and 222 contacts.

        Applied as a guard rather than as a one-off cleanup so it is
        self-healing: whoever adds a zone company to a merchant by hand, from
        the user form or over XML-RPC, gets it taken straight back off.
        """
        zones = self.env["res.company"]._zone_companies()
        if not zones:
            return self.browse()
        changed = self.browse()
        for user in (self - self._zone_company_holders()).sudo():
            surplus = user.company_ids & zones
            if not surplus:
                continue
            user.with_context(**{SKIP_CONTEXT: True}).company_ids = [
                Command.unlink(company.id) for company in surplus
            ]
            changed |= user
        return changed

    @api.model
    def _drop_zone_companies_for_owners(self, companies):
        """Fix every user allowed into ``companies``.

        Called when a shop changes neighbourhood: its people may still be
        carrying the zone company they were given before the guard existed,
        and the one they are carrying is now the wrong one anyway.
        """
        if not companies:
            return self.browse()
        users = (
            self.sudo()
            .with_context(active_test=False)
            .search([("company_ids", "in", companies.ids)])
        )
        return users._drop_zone_companies()

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        if not self.env.context.get(SKIP_CONTEXT):
            users._drop_zone_companies()
        return users

    def write(self, vals):
        res = super().write(vals)
        # Only an ownership edit can bring a zone company in. Reacting to every
        # write would walk the whole user base every time somebody logged in.
        if ("company_ids" in vals or "company_id" in vals) and not self.env.context.get(
            SKIP_CONTEXT
        ):
            self._drop_zone_companies()
        return res
