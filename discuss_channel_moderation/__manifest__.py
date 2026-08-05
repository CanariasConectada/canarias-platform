# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Discuss Channel Moderation",
    "version": "19.0.1.1.0",
    "category": "Discuss",
    "summary": "Pre-moderation of discuss channel comments from untrusted personas",
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Beta",
    "depends": [
        "mail",
    ],
    "data": [
        "security/discuss_channel_moderation_security.xml",
        "security/ir.model.access.csv",
        "security/discuss_channel_moderation_rules.xml",
        "data/discuss_channel_moderation_params.xml",
        "data/mail_template_data.xml",
        "data/ir_cron_data.xml",
        # The pending queue action is referenced by a stat button on the
        # moderation form, so it must be loaded first.
        "views/discuss_channel_pending_message_views.xml",
        "views/discuss_channel_moderation_views.xml",
        "views/discuss_channel_moderation_menus.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
