# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


# The texts a merchant writes in "Contenido de la página". They are declared
# here by name, not imported: ``partner_microsite_manager`` owns the fields and
# this module must keep working (and loading) without it.
MICROSITE_TEXT_FIELDS = (
    "microsite_button_text",
    "microsite_intro_title",
    "microsite_banner_title",
    "microsite_about_title",
    "microsite_about_text",
    "microsite_services_title",
    "microsite_services_text",
    "microsite_parking_info",
    "microsite_delivery_info",
)


# Which of the texts a ``write`` really changes, handed to the mixin.
CHANGED_CONTEXT_KEY = "auto_translate_changed_fields"


class ResCompany(models.Model):
    _name = "res.company"
    _inherit = ["res.company", "auto.translate.mixin"]

    auto_translate_enabled = fields.Boolean(
        string="Translate this shop automatically",
        default=True,
        help="Content owned by this company is queued for automatic "
        "translation whenever it is saved. On by default: a new merchant "
        "company opts into the rollout at birth, so its microsite is born "
        "with the full corporate format (the rollout already covers every "
        "existing shop). Untick it to keep a specific shop out.",
    )

    def _auto_translate_companies(self):
        """Companies opted into the rollout, as a cached-friendly search."""
        return (
            self.env["res.company"]
            .sudo()
            .search([("auto_translate_enabled", "=", True)])
        )

    def _auto_translate_fields(self):
        """The merchant texts that exist, and are translatable, on this database.

        Filtered against the registry so that the module is a no-op when the
        microsite module is not installed, or when it declares a field as a
        plain one.
        """
        return [
            name
            for name in MICROSITE_TEXT_FIELDS
            if name in self._fields and self._fields[name].translate
        ]

    def _auto_translate_scoped(self):
        """Only the shops opted into the rollout."""
        return self.sudo().filtered("auto_translate_enabled")

    def _auto_translate_touched(self, vals):
        """Only the texts whose value really moved.

        The content editor writes the whole form back on every save, so
        "the key is in ``vals``" is true for all nine texts even when the
        merchant only fixed a comma. ``write`` records which ones differ
        before the new values land.
        """
        changed = self.env.context.get(CHANGED_CONTEXT_KEY)
        if changed is None:
            return super()._auto_translate_touched(vals)
        return [
            name for name in super()._auto_translate_touched(vals) if name in changed
        ]

    def write(self, vals):
        names = [name for name in self._auto_translate_fields() if name in vals]
        if not names:
            return super().write(vals)
        changed = sorted(
            name
            for name in names
            if any(
                (company[name] or False) != (vals[name] or False) for company in self
            )
        )
        return super(
            ResCompany, self.with_context(**{CHANGED_CONTEXT_KEY: changed})
        ).write(vals)
