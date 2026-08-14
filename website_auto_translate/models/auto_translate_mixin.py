# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models


class AutoTranslateMixin(models.AbstractModel):
    """Queue a translation whenever somebody saves translatable content.

    The work itself never happens here. A merchant saving a product must not
    wait for a translation service, and must not have their save fail because
    that service is down -- so saving only writes a row, and a cron does the
    talking.
    """

    _name = "auto.translate.mixin"
    _description = "Automatic Translation Mixin"

    def _auto_translate_fields(self):
        """Field names worth translating. Override per model."""
        return []

    def _auto_translate_touched(self, vals):
        """Which translatable fields a given ``write`` actually changed.

        Separate from :meth:`_auto_translate_fields` because the field that
        stores the text is not always the field that gets written: the website
        builder saves ``ir.ui.view.arch``, an inverse onto ``arch_db``, so
        matching the stored name against ``vals`` would never fire for pages.
        """
        return [name for name in self._auto_translate_fields() if name in vals]

    def _auto_translate_scoped(self):
        """The subset of ``self`` covered by the rollout.

        Deliberately a recordset filter rather than a per-record test: models
        that scope by company would otherwise re-read the company table once
        per product on every save.

        Default is "everything"; models that belong to a company narrow it down
        so the rollout can start with the portal and the three commercial zones
        instead of all 216 shops at once.
        """
        return self

    @api.model
    def _auto_translate_target_langs(self):
        """Every active language except the one content is written in."""
        source = self._auto_translate_source_lang()
        langs = self.env["res.lang"].sudo().search([("active", "=", True)])
        return [lang.code for lang in langs if lang.code != source]

    @api.model
    def _auto_translate_source_lang(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("website_auto_translate.source_lang", "es_ES")
        )

    @api.model
    def _auto_translate_active(self):
        """Whether automatic translation is switched on at all.

        Odoo stores a boolean setting as the string ``"True"`` and *deletes*
        the parameter when it is turned off, so this deliberately does not
        trust a plain truthiness test.
        """
        value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("website_auto_translate.enabled")
        )
        return value in ("True", "true", "1")

    def _auto_translate_enqueue(self, field_names):
        if not field_names or self.env.context.get("auto_translate_skip"):
            return
        if not self._auto_translate_active():
            return
        # Somebody editing the German page is not editing the source, and
        # queueing that would have us overwrite what they just typed.
        langs = self._auto_translate_target_langs()
        if self.env.lang and self.env.lang in langs:
            return
        in_scope = self._auto_translate_scoped()
        if not in_scope:
            return
        self.env["auto.translate.job"].sudo()._enqueue_many(
            in_scope, field_names, langs
        )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._auto_translate_enqueue(records._auto_translate_fields())
        return records

    def write(self, vals):
        result = super().write(vals)
        touched = self._auto_translate_touched(vals)
        if touched:
            self._auto_translate_enqueue(touched)
        return result
