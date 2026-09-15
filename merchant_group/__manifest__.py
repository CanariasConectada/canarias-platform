# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Merchant Group",
    "version": "19.0.2.0.0",
    "category": "Tools",
    "summary": "One group that makes a user a merchant, given to every new user",
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "development_status": "Production/Stable",
    "depends": [
        # Every module below owns a group the merchant group implies, a
        # menu this module re-gates, or a model it grants access to; naming
        # a record whose module is absent aborts the install, so each one
        # is a real dependency rather than a hope.
        "sale",
        "product",
        "website",
        "mass_mailing",
        "company_certification",
        "partner_reviews",
        "crm",
        "purchase",
        "stock",
        "account",
        "sale_loyalty",
        "website_sale_loyalty",
        "board",
        "spreadsheet_dashboard",
        "project_todo",
    ],
    "data": [
        "security/merchant_group.xml",
        "security/ir.model.access.csv",
        "views/menu_gating.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
