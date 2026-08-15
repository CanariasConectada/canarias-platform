# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Website Auto Translate",
    "summary": "Translate shop, event and page content automatically when it is saved",
    "version": "19.0.2.0.0",
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "category": "Website",
    "license": "AGPL-3",
    "depends": ["website", "website_sale", "event"],
    "data": [
        "security/ir.model.access.csv",
        "data/auto_translate_engine_data.xml",
        "data/auto_translate_glossary_data.xml",
        "data/ir_cron.xml",
        "views/auto_translate_engine_views.xml",
        "views/auto_translate_glossary_views.xml",
        "views/auto_translate_job_views.xml",
        "views/res_company_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
