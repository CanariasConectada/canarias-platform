# Copyright 2026 Canarias Conectada
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import _, api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # Both policies default to "hidden" so installing the module never puts a
    # claim on a product page that the shop has not written itself.
    return_warranty = fields.Selection(
        [
            ("hidden", "Hidden"),
            ("none", "No return warranty"),
            ("14_days", "14 days"),
            ("30_days", "30 days"),
            ("60_days", "60 days"),
            ("90_days", "90 days"),
            ("custom", "Custom"),
        ],
        string="Return warranty",
        default="hidden",
        help="Return policy shown on the product page. Replaces the returns "
        "text Odoo hardcodes for every product.",
    )
    return_warranty_custom_value = fields.Integer(
        string="Return warranty value",
        default=0,
    )
    return_warranty_custom_period = fields.Selection(
        [
            ("days", "Days"),
            ("weeks", "Weeks"),
            ("months", "Months"),
            ("years", "Years"),
        ],
        string="Return warranty period",
        default="days",
    )

    delivery_days = fields.Selection(
        [
            ("hidden", "Hidden"),
            ("none", "No home delivery"),
            ("24h", "24 hours"),
            ("2_3_days", "2-3 days"),
            ("3_5_days", "3-5 days"),
            ("5_7_days", "5-7 days"),
            ("custom", "Custom"),
        ],
        string="Delivery time",
        default="hidden",
        help="Delivery time shown on the product page. Replaces the shipping "
        "text Odoo hardcodes for every product.",
    )
    delivery_days_custom_value = fields.Integer(
        string="Delivery time value",
        default=0,
    )
    delivery_days_custom_period = fields.Selection(
        [
            ("hours", "Hours"),
            ("days", "Days"),
            ("weeks", "Weeks"),
        ],
        string="Delivery time period",
        default="days",
    )

    # The sentence shown on the public page is built here rather than in QWeb:
    # a translatable QWeb text node that sits next to an <i> icon is extracted
    # with the icon markup and the surrounding indentation baked into the
    # msgid, which makes the .po entry unusable in practice.
    return_warranty_display = fields.Char(
        string="Return warranty text",
        compute="_compute_return_warranty_display",
    )
    delivery_days_display = fields.Char(
        string="Delivery time text",
        compute="_compute_delivery_days_display",
    )

    @api.depends(
        "return_warranty",
        "return_warranty_custom_value",
        "return_warranty_custom_period",
    )
    def _compute_return_warranty_display(self):
        for product in self:
            policy = product.return_warranty
            if not policy or policy == "hidden":
                product.return_warranty_display = False
            elif policy == "none":
                product.return_warranty_display = _("No return warranty")
            else:
                if policy == "custom":
                    period = "%s %s" % (
                        product.return_warranty_custom_value,
                        product._return_warranty_period_label(),
                    )
                else:
                    period = {
                        "14_days": _("14 days"),
                        "30_days": _("30 days"),
                        "60_days": _("60 days"),
                        "90_days": _("90 days"),
                    }[policy]
                product.return_warranty_display = _(
                    "Return warranty: %(period)s", period=period
                )

    @api.depends(
        "delivery_days",
        "delivery_days_custom_value",
        "delivery_days_custom_period",
    )
    def _compute_delivery_days_display(self):
        for product in self:
            policy = product.delivery_days
            if not policy or policy == "hidden":
                product.delivery_days_display = False
            elif policy == "none":
                product.delivery_days_display = _("No home delivery")
            else:
                if policy == "custom":
                    period = "%s %s" % (
                        product.delivery_days_custom_value,
                        product._delivery_days_period_label(),
                    )
                else:
                    period = {
                        "24h": _("24 hours"),
                        "2_3_days": _("2-3 days"),
                        "3_5_days": _("3-5 days"),
                        "5_7_days": _("5-7 days"),
                    }[policy]
                product.delivery_days_display = _(
                    "Delivery in %(period)s", period=period
                )

    def _return_warranty_period_label(self):
        self.ensure_one()
        return {
            "days": _("days"),
            "weeks": _("weeks"),
            "months": _("months"),
            "years": _("years"),
        }.get(self.return_warranty_custom_period or "days", _("days"))

    def _delivery_days_period_label(self):
        self.ensure_one()
        return {
            "hours": _("hours"),
            "days": _("days"),
            "weeks": _("weeks"),
        }.get(self.delivery_days_custom_period or "days", _("days"))
