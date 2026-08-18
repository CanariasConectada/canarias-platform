# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Discuss Community Moderation",
    "version": "19.0.1.0.0",
    "category": "Discuss",
    "summary": "Pre-moderation of community guests and new community members, "
    "with the pending state rendered inside the Discuss client",
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Beta",
    "depends": [
        # The engine: the per-channel switch row, the hold funnel and the
        # held-payload model this module extends. Its gates and semantics are
        # NOT modified here -- everything below is additive inheritance.
        "discuss_channel_moderation",
        # The population: community members are INTERNAL users carrying
        # `group_community_member`, community guests are internal users
        # flagged `is_community_guest`. Neither is a `mail.guest`, so the
        # engine's `moderate_guests` never covers them -- that gap is the
        # whole reason this bridge exists.
        "discuss_community",
    ],
    "data": [
        "views/discuss_channel_moderation_views.xml",
    ],
    "assets": {
        # Backend only, on purpose: community members and community guests
        # are internal users whose whole backend IS the Discuss client
        # (`discuss_community` strips everything else). Anonymous
        # `mail.guest` personas never load this bundle -- their pending
        # state is rendered by `website_pwa_chat` on the frontend.
        "web.assets_backend": [
            "discuss_community_moderation/static/src/backend/*",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
