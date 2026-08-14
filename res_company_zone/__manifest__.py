# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Res Company Zone",
    "version": "19.0.1.0.0",
    "category": "Website",
    "summary": "Commercial zone of each business, feeding the public directory",
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
    """,
    "author": "MikeColangelo",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Beta",
    "depends": [
        "website_directory",
    ],
    "data": [
        "views/res_company_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
