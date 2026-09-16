# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

# Whoever holds one of these curates the platform, not a shop: the record
# rules hand them every category back (see security/ir_rule.xml) and this
# guard leaves their values alone. `base.group_system` is the administrator;
# `website.group_website_designer` is what `zca_platform` grants its staff.
_UNRESTRICTED_GROUPS = ("base.group_system", "website.group_website_designer")


class ProductPublicCategory(models.Model):
    _inherit = "product.public.category"

    def _wsmc_is_restricted_merchant(self):
        """True when the caller is a merchant and nothing more.

        A merchant may create and edit categories (ACL in this module) but
        only categories of their own site; the record rules enforce that on
        existing records and this decides whether the values they SEND get
        pinned. ``sudo`` and the platform's own people are never pinned.
        """
        if self.env.su:
            return False
        user = self.env.user
        if any(user.has_group(group) for group in _UNRESTRICTED_GROUPS):
            return False
        return user.has_group("merchant_group.group_merchant")

    def _wsmc_pin_website(self, vals, current=None):
        """Force ``website_id`` in ``vals`` to a site the merchant owns.

        Whatever they sent -- another shop's site, nothing, ``False`` (which
        would make a SHARED category every other shop sees) -- the category
        ends up on one of their own sites: the one they asked for when it is
        theirs, else the site of the shop they are working in (``current``,
        the record being written, or the session company's site). A merchant
        with no site of their own cannot own a category at all.
        """
        Website = self.env["website"]
        allowed = Website._wsmc_merchant_websites()
        if not allowed:
            raise UserError(Website._wsmc_no_shop_message())
        wanted = vals.get("website_id")
        if wanted and wanted in allowed.ids:
            vals["website_id"] = wanted
            return vals
        if current and current in allowed.ids:
            vals["website_id"] = current
            return vals
        session = self.env.company.website_id
        vals["website_id"] = (
            session.id if session in allowed else allowed.sorted("id")[0].id
        )
        return vals

    def _wsmc_check_parent(self, vals, website_id):
        """A merchant's category hangs under one of their own, or under none.

        A shared parent would let a merchant reshape the platform's tree
        from below (their child would render under the shared node on every
        site listing it); another shop's parent is simply not theirs.
        """
        parent_id = vals.get("parent_id")
        if not parent_id:
            return
        parent = self.browse(parent_id).sudo()
        if parent.website_id.id != website_id:
            raise AccessError(
                _(
                    "%(parent)s is not one of your own categories. Your "
                    "categories can only hang under a category of your own "
                    "shop, or under none.",
                    parent=parent.display_name,
                )
            )

    @api.model_create_multi
    def create(self, vals_list):
        if self._wsmc_is_restricted_merchant():
            for vals in vals_list:
                self._wsmc_pin_website(vals)
                self._wsmc_check_parent(vals, vals["website_id"])
        return super().create(vals_list)

    def write(self, vals):
        if self._wsmc_is_restricted_merchant() and (
            "website_id" in vals or "parent_id" in vals
        ):
            allowed_ids = set(self.env["website"]._wsmc_merchant_websites().ids)
            # The record rule already refuses a category that is not theirs;
            # what is decided here is where THEIR category may go.
            if "website_id" in vals and vals["website_id"] not in allowed_ids:
                raise AccessError(
                    _(
                        "A category of your shop stays on your shop's site: "
                        "it cannot be moved to another site or made shared."
                    )
                )
            if "parent_id" in vals:
                for category in self:
                    self._wsmc_check_parent(
                        vals, vals.get("website_id", category.website_id.id)
                    )
        return super().write(vals)

    # Merchants edit their own categories from a form that shows the site
    # read-only; the default has to be there for the pin to be visible.
    website_id = fields.Many2one(default=lambda self: self._wsmc_default_website())

    def _wsmc_default_website(self):
        """The merchant's own site as the default of a new category.

        Only for restricted merchants: for everyone else the core default
        (none, a shared category) stays, so an administrator creating a
        category from the eCommerce menu is unaffected.
        """
        if not self._wsmc_is_restricted_merchant():
            return False
        allowed = self.env["website"]._wsmc_merchant_websites()
        session = self.env.company.website_id
        if session in allowed:
            return session.id
        return allowed[:1].id or False
