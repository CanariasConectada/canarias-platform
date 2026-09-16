# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models


class IrUiMenu(models.Model):
    """Strip the backend down to Discuss for community members.

    WHY here and not on the menus themselves: a menu with NO groups is visible
    to every internal user (``_visible_menu_ids`` keeps any row whose
    ``group_ids`` is empty), so hiding the rest of the backend declaratively
    would mean writing ``group_ids`` on every other root menu -- core rows
    owned by every installed app, re-added by every future module, reset by
    upgrades. Filtering the VISIBLE SET at its single choke point instead
    touches nothing: ``_visible_menu_ids`` is what ``load_menus`` (the web
    client's menu payload) and ``_filter_visible_menus`` both consume, so one
    override covers every consumer, survives upgrades, and follows new apps
    automatically.

    Cache note: the core method is ``ormcache``-d on the user's group ids;
    this override wraps OUTSIDE that cache (the decorator sits on the base
    function), so the expensive computation stays cached per group-set while
    the community filter -- one indexed ``child_of`` search and a set
    intersection -- runs per call. Cheap, and always fresh.
    """

    _inherit = "ir.ui.menu"

    @api.model
    def _visible_menu_ids(self, debug=False):
        visible = super()._visible_menu_ids(debug=debug)
        user = self.env.user
        if not user.has_group("discuss_community.group_community_member"):
            return visible
        # Never strip an administrator: if staff ever ends up holding the
        # community group (a support login, a misconfigured role), a locked
        # Settings menu must not be the way anybody finds out.
        if user.has_group("base.group_system"):
            return visible
        discuss_root = self.env.ref("mail.menu_root_discuss", raise_if_not_found=False)
        if not discuss_root:
            # No Discuss to strip down TO: fail open rather than render an
            # empty backend.
            return visible
        allowed = self.sudo().search([("id", "child_of", discuss_root.id)])
        return frozenset(visible & set(allowed.ids))
