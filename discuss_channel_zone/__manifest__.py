# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Discuss Channel Zone",
    "version": "19.0.1.0.0",
    "category": "Discuss",
    "summary": "Community chat channels seeded per commercial zone, with "
    "membership derived from each user's zone",
    "description": """
        Seeds the four community channels of the platform -- one general
        channel open to everyone (visitors included) and one closed channel per
        neighbourhood (Guanarteme, Tamaraceite, Lomo los Frailes) -- and keeps
        membership of them in sync with each user's zone.

        A merchant's zone comes from their company. A resident with no business
        picks their own. Nobody joins or leaves by hand: membership is a
        function of the account, reconciled on create, on the writes that can
        change the answer, and nightly.
    """,
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Beta",
    "depends": [
        # The `discuss.channel.moderation` rows seeded in data/ are rows of
        # THIS model, and `mail` comes in with it. All four channels ship
        # pre-moderated for guests, so the dependency is hard, not optional.
        "discuss_channel_moderation",
        # `res.company.commercial_zone` (the merchant's zone) and
        # `_normalise_zone` (the legacy spellings) both live here. It also
        # drags in `website_directory`, which is where `ZONE_SELECTION` and
        # `res.company._get_own_company_for_directory` are defined -- the
        # selection this module reuses and the "usable company" rule it
        # mirrors.
        "res_company_zone",
    ],
    "data": [
        # The group is referenced by the zone channels, so it must exist first.
        "security/discuss_channel_zone_groups.xml",
        "data/discuss_channel_data.xml",
        "data/ir_cron_data.xml",
        "views/res_users_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
}
