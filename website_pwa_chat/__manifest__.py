# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Website PWA Chat",
    "version": "19.0.5.0.0",
    "category": "Website",
    "summary": "Community chat page of the Canarias Conectada app, served "
    "inside the public website layout",
    "description": """
        The /chat page of the unified app: the visitor picks one of the
        community channels they are allowed to see and reads, writes and
        follows the conversation live -- without leaving the PWA.

        Deliberately NOT built on core's /discuss/channel/<id> public page.
        That page renders `mail.discuss_public_channel_template`, a standalone
        <html> shell with its own <head>: no manifest link, no theme, no
        website menu. A visitor who reached it from the installed app would
        leave the app without being told. This page renders inside
        `website.layout`, so it is part of the app like any other page.

        Also deliberately NOT built on `im_livechat`'s embedded Discuss
        components -- see readme/DESCRIPTION.md for why that dependency was
        weighed and refused.
    """,
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Beta",
    "depends": [
        # The app shell. `website.layout` gets the manifest link, the theme
        # colour and the apple-* tags from this module, which is the whole
        # reason the chat is a website page and not core's standalone Discuss
        # shell. Brings in `website` (and with it `auth_signup`, which the
        # "create your account" call to action links to).
        "website_pwa",
        # WHAT the page lists. The four seeded channels and, more importantly,
        # the group that closes the three zone channels to visitors: this
        # module never decides who may see what, it only renders the result of
        # a `search()` that `ir_rule_discuss_channel_all` already filtered.
        "discuss_channel_zone",
        # WHY a guest's message does not appear immediately. The page has to
        # read `discuss.channel.pending.message` to show its author the "en
        # revisión" state, and has to understand `message_id: False` coming
        # back from /mail/message/post. Both are this module's contract.
        "discuss_channel_moderation",
        # The live half. `bus` is the ONE messaging bundle core already ships
        # in `web.assets_frontend`, which is what makes a self-contained
        # frontend chat possible without pulling `im_livechat`'s embed bundle
        # onto every website of the platform. `discuss_channel_zone` drags
        # `mail` in anyway, but not `bus`, so it is declared here.
        "bus",
    ],
    "data": [
        # The support group is referenced by the cron's own reasoning and by
        # `_support_agents`, so it exists before anything can look for it.
        "security/website_pwa_chat_groups.xml",
        "views/website_views.xml",
        "views/templates.xml",
        # After the group it is gated on and after the templates, so the
        # backend queue can be read by the same people who answer it.
        "views/support_views.xml",
        "data/discuss_channel_data.xml",
        "data/ir_cron_data.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_pwa_chat/static/src/js/community_chat.js",
            "website_pwa_chat/static/src/js/support_window.js",
            "website_pwa_chat/static/src/scss/community_chat.scss",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
