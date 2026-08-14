# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


class CertificationMaterial(models.Model):
    """A downloadable training document of one certification vertical.

    Merchants read these to prepare before taking the questionnaire. The file
    itself lives in a plain ``ir.attachment`` so Odoo serves it through
    ``/web/content`` with no controller of our own; this model only adds the
    ordering, the title and the vertical it belongs to.

    Keeping the material as DATA (rather than files shipped inside the module)
    is what lets a new vertical be added without touching code, exactly like
    the rest of ``certification.type``.
    """

    _name = "certification.material"
    _description = "Certification Training Material"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    type_id = fields.Many2one(
        "certification.type",
        string="Certification",
        required=True,
        ondelete="cascade",
        index=True,
    )
    description = fields.Char(
        translate=True, help="One line shown under the title on the landing page."
    )
    attachment_id = fields.Many2one(
        "ir.attachment",
        string="File",
        required=True,
        ondelete="cascade",
        help="The document merchants download.",
    )
    download_url = fields.Char(compute="_compute_download_url")

    @api.depends("attachment_id")
    def _compute_download_url(self):
        for material in self:
            attachment = material.attachment_id
            material.download_url = (
                f"/web/content/{attachment.id}?download=true" if attachment else False
            )

    def _publish_attachments(self):
        """Make the linked files publicly readable.

        The landing page is ``auth="public"``: a private attachment would
        answer 403 to exactly the visitors this material exists for. Attaching
        a document here IS the act of publishing it, so the flag follows the
        link instead of being a second step an admin can forget.
        """
        attachments = self.mapped("attachment_id").sudo()
        attachments.filtered(lambda a: not a.public).write({"public": True})

    @api.model_create_multi
    def create(self, vals_list):
        materials = super().create(vals_list)
        materials._publish_attachments()
        return materials

    def write(self, vals):
        result = super().write(vals)
        if "attachment_id" in vals:
            self._publish_attachments()
        return result
