# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Merchant Group",
    "version": "19.0.1.0.0",
    "category": "Tools",
    "summary": "One group that makes a user a merchant, given to every new user",
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "development_status": "Production/Stable",
    "depends": [
        # Every module below owns one of the groups the merchant group
        # implies; naming a group whose module is absent aborts the install,
        # so each one is a real dependency rather than a hope.
        "sale",
        "product",
        "website",
        "mass_mailing",
        "company_certification",
        "partner_reviews",
    ],
    "data": ["security/merchant_group.xml"],
    "installable": True,
    "application": False,
    "auto_install": False,
}
