# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    auto_translate_enabled = fields.Boolean(
        string="Translate content automatically",
        config_parameter="website_auto_translate.enabled",
    )
    auto_translate_source_lang = fields.Selection(
        selection="_auto_translate_lang_get",
        string="Content is written in",
        default="es_ES",
        config_parameter="website_auto_translate.source_lang",
    )
    auto_translate_mode = fields.Selection(
        [
            ("single", "One engine"),
            ("jury", "Jury: every engine translates, an arbiter picks"),
        ],
        string="How to translate",
        default="single",
        config_parameter="website_auto_translate.mode",
    )
    auto_translate_engine_id = fields.Many2one(
        "auto.translate.engine",
        string="Engine",
        config_parameter="website_auto_translate.engine_id",
    )
    auto_translate_batch_size = fields.Integer(
        string="Texts per run",
        default=50,
        config_parameter="website_auto_translate.batch_size",
    )

    @api.model
    def _auto_translate_lang_get(self):
        langs = self.env["res.lang"].get_installed()
        return [(code, name) for code, name in langs]

    def action_open_auto_translate_engines(self):
        return self.env["ir.actions.act_window"]._for_xml_id(
            "website_auto_translate.action_auto_translate_engine"
        )

    def action_open_auto_translate_jobs(self):
        return self.env["ir.actions.act_window"]._for_xml_id(
            "website_auto_translate.action_auto_translate_job"
        )
