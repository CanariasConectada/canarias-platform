# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    def set_groups_from_roles(self, force=False):
        """Additive sync: the role is a floor, not a ceiling.

        Upstream replaces ``group_ids`` with exactly the union of the
        enabled roles' groups -- and it runs on every ``res.users.write``,
        so a group granted by hand to one particular user is silently
        reverted moments later. Asked for on 2026-09-02: "quiero que lo
        usemos de modo de plantilla [...] pero no quiero que me bloquee la
        posibilidad de asignarle una u otra cosa a este usuario".

        So the sync only ever ADDS what the roles imply. Three consequences,
        all wanted:

        * assigning a role still applies everything it carries;
        * a hand-granted extra survives every later write and the nightly
          ``cron_update_users``;
        * a role-implied group removed by hand is healed back -- the role
          stays the guaranteed minimum, which is what makes it a template
          rather than a suggestion.

        ``force=True`` -- role lines being unlinked -- keeps the upstream
        full replacement: taking a role away must take its groups away, and
        that reset is the moment hand-granted extras are deliberately wiped
        too, so an account whose role changes starts from a clean template.
        """
        if force:
            return super().set_groups_from_roles(force=True)
        for user in self:
            if not user.role_line_ids:
                continue
            wanted = user._get_enabled_roles().role_id.all_implied_ids
            missing = wanted - user.group_ids
            if missing:
                # This write re-enters the ``base_user_role`` sync once; the
                # second pass finds nothing missing and stops, so no guard
                # flag is needed -- additive syncs are naturally idempotent.
                super(ResUsers, user).write(
                    {"group_ids": [fields.Command.link(g.id) for g in missing]}
                )
        return True

    @api.depends("role_line_ids")
    def _compute_show_alert(self):
        """Retire the "changes will not be persistent" banner.

        It warned about the exact behaviour this module removes: with the
        additive sync, a change made on the Access Rights tab IS persistent.
        Keeping the banner would train administrators to distrust a screen
        that now works.
        """
        self.show_alert = False
