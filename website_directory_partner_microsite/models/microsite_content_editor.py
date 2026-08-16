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
        # Read through the directory's own notion of "your company", which is
        # the one its writer will use in a moment. They agree today -- both
        # are `res.users.company_id` -- and reading through the same door is
        # what keeps them agreeing.
        company = self.env["res.company"]._get_own_company_for_directory()
        values["directory_category_id"] = company.category_id.id if company else False
        return values

    def action_save(self):
        """Save the page first, then the category.

        Deliberately NOT added to ``_editable_field_names()``: that list is
        written straight onto ``res.company`` with sudo, and the category
        needs checks the whitelist knows nothing about -- it has to exist, be
        active, and not be a folder. ``set_own_directory_category`` already
        owns all three, and is reachable over XML-RPC, so it is the single
        place that decides.

        Both writes are in one transaction, so a rejected category takes the
        rest of the screen back with it rather than leaving half of it saved.
        """
        result = super().action_save()
        self.env["res.company"].set_own_directory_category(
            self.directory_category_id.id or False
        )
        return result
