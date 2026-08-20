# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Discuss Community",
    "version": "19.0.1.2.0",
    "category": "Discuss",
    "summary": "Community members (residents and walk-in guests) as internal "
    "users whose whole backend is Discuss",
    "description": """
        Phase 1 of moving the "Comunidad" experience into the Discuss backend.

        Residents who sign up on any of the platform's websites, and visitors
        who walk in through the "Enter as guest" button, become lightweight
        INTERNAL users carrying the Community Member group. Their backend is
        stripped down to Discuss (every other root menu disappears), they land
        straight in Discuss after login, and the website they arrived on
        decides the neighbourhood channel they are seated in.

        Merchants and platform staff are untouched: the website-of-arrival
        tier applies only to NEW community members, and a backend-invited
        portal user stays portal.
    """,
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Beta",
    "depends": [
        # Discuss itself: the one app a community member keeps, the
        # `mail.action_discuss` landing action and the `mail.menu_root_discuss`
        # root the menu stripping pivots on.
        "mail",
        # The arrival website is what decides the community zone.
        "website",
        # The self-registration flow this module bends: a signup that happens
        # on a website produces a community member instead of a portal user.
        "auth_signup",
        # `chat_zone`, `_zone_channel` / `_sync_zone_channels` and the
        # portal-OR-internal `group_zone_channel_member` gate all live here.
        "discuss_channel_zone",
        # `_find_login_website`: the canonical, Host-header-safe resolver of
        # "which website is this request being served by". Reused, not
        # duplicated (its predecessor had a substring-match vulnerability).
        "website_login_company",
        # The guest blueprint this module mirrors for INTERNAL guests: the
        # non-routable login domain constant, the signed reuse-cookie pattern
        # and the branded card styling the /community page reuses.
        "website_login_branding",
    ],
    "data": [
        "security/discuss_community_groups.xml",
        "data/ir_cron.xml",
        "views/community_templates.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
