# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "ZCA Manager Group",
    "version": "19.0.1.0.0",
    "category": "Tools",
    "summary": "One group that makes a user the manager of a commercial zone",
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "development_status": "Production/Stable",
    "depends": [
        # Every module below owns a group the manager group implies, a
        # menu this module hangs from or re-gates, or a field a record
        # rule reads; naming a record whose module is absent aborts the
        # install, so each one is a real dependency rather than a hope.
        "contacts",
        "event",
        # ``is_published`` on the event and the zone website the event
        # defaults to.
        "website_event",
        "mass_mailing",
        # ``res.company.zone_company_key`` (which company IS a zone) and,
        # through ``res_company_zone``, ``commercial_zone`` (which zone a
        # shop belongs to). The partner ownership sync of this module is
        # what makes the zone's contacts visible without a rule here.
        "zone_company_ownership",
        # The zone chat channel the manager is seated in.
        "discuss_channel_zone",
        # Owns the Website > Site > Content > Products entry re-gated here.
        "website_sale",
    ],
    "data": [
        "security/zca_manager_group.xml",
        "views/menu_gating.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
