# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Moderation: Forbidden Words",
    "version": "19.0.1.0.0",
    "category": "Website",
    "summary": "One administrator-managed forbidden-word list shared by every "
    "moderated text on the platform",
    "author": "MikeColangelo",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Production/Stable",
    "depends": ["base"],
    "data": [
        "security/ir.model.access.csv",
        "views/moderation_forbidden_word_views.xml",
        "views/moderation_menus.xml",
        "data/forbidden_words.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
