# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models


class LocalContentItemStart(models.TransientModel):
    """Ask what is being created before opening the form.

    One list holds memoria viva and lugares de interés together, which is the
    right shape to READ them in and the wrong one to CREATE in: plain "New"
    opens a blank record that could become either, and the answer sits eight
    fields down inside a group called Classification.

    So the question is asked first, on its own screen, and the answer is
    carried into the form as a default. The type stays editable there -- this
    is a shortcut through the form, never a second set of rules about it.
    """

    _name = "website.local.content.item.start"
    _description = "New local content item"

    type_id = fields.Many2one(
        comodel_name="website.local.content.type",
        string="What are you creating",
        required=True,
        default=lambda self: self._default_type_id(),
        help="Memoria viva, lugares de interés, or any other content type "
        "configured on the platform.",
    )
    name = fields.Char(
        string="Title",
        help="Optional. Fills in the title of the new entry so the form opens "
        "with something in it; it can be changed there like any other field.",
    )

    def _default_type_id(self):
        """Pre-select when there is nothing to choose between.

        With a single content type configured the question has one possible
        answer, and asking it anyway would be ceremony.
        """
        types = self.env["website.local.content.type"].search([], limit=2)
        return types if len(types) == 1 else False

    def action_create(self):
        """Open the item form already knowing what it is.

        ``default_category_id`` is deliberately NOT set. The category is
        required and its domain follows the type, so guessing one would put a
        value in front of the author that they did not choose and that the
        type may not even allow.
        """
        self.ensure_one()
        context = dict(self.env.context, default_type_id=self.type_id.id)
        if self.name:
            context["default_name"] = self.name
        return {
            "type": "ir.actions.act_window",
            "name": _("New %s", self.type_id.name),
            "res_model": "website.local.content.item",
            "view_mode": "form",
            "target": "current",
            "context": context,
        }
