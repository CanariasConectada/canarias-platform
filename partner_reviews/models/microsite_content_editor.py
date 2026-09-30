# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

# What the merchant may change about their reviews page from their own
# content editor: whether it exists, and nothing else.
REVIEW_FIELDS = ("enable_reviews",)


class MicrositeContentEditor(models.TransientModel):
    """Let the merchant switch their own reviews page on and off.

    Client request 2026-09-16: the switch lived on the company form alone,
    which no merchant can save, so every shop that wanted a reviews page had
    to ask for it. The value travels through the editor's whitelist
    (``_editable_field_names``), so it is written with the same ownership
    check as the rest of the page content, and the company's ``write`` adds
    or removes the *Reviews* entry of the shop's website menu on its own.
    """

    _inherit = "microsite.content.editor"

    enable_reviews = fields.Boolean(
        string="Enable reviews page",
        help="Publish a page on your website where your customers can rate "
        "your shop and leave comments.",
    )
    review_avg = fields.Float(
        string="Average rating",
        digits=(3, 1),
        compute="_compute_review_info",
    )
    review_count = fields.Integer(
        string="Published reviews",
        compute="_compute_review_info",
    )
    reviews_page_url = fields.Char(
        string="Reviews page",
        compute="_compute_review_info",
    )

    def _editable_field_names(self):
        return super()._editable_field_names() + list(REVIEW_FIELDS)

    @api.depends("company_id")
    def _compute_review_info(self):
        """Figures of the shop this screen edits, and only of a shop the
        caller may edit: ``company_id`` comes back from the browser, so it is
        checked against the same authority the save goes through instead of
        being read blindly with sudo."""
        editable = self.env["res.company"]._get_editable_microsite_companies()
        for editor in self:
            company = editor.company_id & editable
            company = company.sudo()
            editor.review_avg = company.review_avg if company else 0.0
            editor.review_count = company.review_count if company else 0
            editor.reviews_page_url = company.reviews_page_url if company else False
