# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class MicrositeContentEditor(models.TransientModel):
    """Let the merchant say which category their shop is listed under.

    Reported on 2026-08-16: "los etiquetas del comercio deben estar disponible
    para editar por el usuario" -- the directory category.

    It already was, technically. ``/mi-comercio`` has done exactly this since
    July, with the company resolved from the session and a folder category
    refused. What it never had was a way in: no website menu points at it, no
    button links to it, and a page you reach only by typing the URL is not a
    page a merchant has.

    So the field moves to the screen where they now edit the rest of their
    page, and the write goes through the same hardened method rather than a
    second copy of it.
    """

    _inherit = "microsite.content.editor"

    directory_category_id = fields.Many2one(
        comodel_name="res.company.category",
        string="Category in the directory",
        # A "view" category only groups other categories. The domain is a
        # hint; `set_own_directory_category` is what actually refuses one.
        domain="[('type', '=', 'normal')]",
        help="How your shop is filed in the business directory at /comercio. "
        "Leave it empty to be listed without a category.",
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        # Read the category off the SAME company the base screen just
        # resolved (`values["company_id"]`), not off a second, independent
        # session lookup: a picker can now open this screen on a DIFFERENT
        # shop than the session's, and the two resolutions must never be
        # allowed to disagree about which company is being edited.
        company_id = values.get("company_id")
        # sudo: a merchant can read res.company today, but this screen must
        # not stop working the day that ACL is tightened (same reasoning as
        # the base screen's own default_get).
        company = self.env["res.company"].sudo().browse(company_id) if company_id else None
        values["directory_category_id"] = company.category_id.id if company else False
        return values

    def action_save(self):
        """Save the page first, then the category, on the SAME resolved shop.

        Deliberately NOT added to ``_editable_field_names()``: that list is
        written straight onto ``res.company`` with sudo, and the category
        needs checks the whitelist knows nothing about -- it has to exist, be
        active, and not be a folder. ``_set_directory_category_checked``
        already owns all three, and is reachable over XML-RPC, so it is the
        single place that decides -- called here on the company
        ``_resolve_target_company`` already validated for this very save, so
        a picker choice never lets the category land on a different shop
        than the one the page content just landed on.

        Both writes are in one transaction, so a rejected category takes the
        rest of the screen back with it rather than leaving half of it saved.
        """
        result = super().action_save()
        company = self._resolve_target_company(
            self.env.context.get("microsite_company_id") or self.company_id.id
        )
        company._set_directory_category_checked(self.directory_category_id.id or False)
        return result
