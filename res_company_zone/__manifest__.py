# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Res Company Zone",
    "version": "19.0.1.2.0",
    "category": "Website",
    "summary": "Commercial zone and trade name of each business, on the company",
    "description": """
        Stores the neighbourhood (Guanarteme, Tamaraceite, Lomo los Frailes)
        a business belongs to, and feeds it to the directory entry.

        website_directory shipped _get_directory_zone() as an explicit
        extension hook returning the global zone "until the new zone module
        lands". This is that module.

        Without it the zone existed only on the directory entry, defaulted to
        "canarias" for everyone, and the migration had nowhere to put the
        legacy value: 264 of 274 businesses sat in the global zone while the
        old database knew Guanarteme 168, Tamaraceite 44 and Lomo los Frailes
        32. The public zone filter was therefore empty in practice.

        It also lets the company answer to its trade name (l10n_es_partner's
        field on the partner): the Settings list, the search box and every
        company dropdown match and show "TRADE NAME (Legal Name)", because
        the legal name is the owner's own name for a third of the shops and
        nobody types it first.
    """,
    "author": "MikeColangelo",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Beta",
    "depends": [
        "website_directory",
        "l10n_es_partner",
        "res_company_search_view",
    ],
    "data": [
        "views/res_company_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
