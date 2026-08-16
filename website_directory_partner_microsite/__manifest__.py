# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Website Directory - Merchant Self-Service",
    "version": "19.0.1.0.0",
    "category": "Website",
    "summary": "Set the directory category from the merchant's own page-content screen",
    "description": """
        The category a shop is listed under in the directory was already the
        merchant's to change -- `/mi-comercio` has done it since July, with
        every guard it needs. Nothing has ever linked to that page, so in
        practice it was the merchant's to change only if they knew the URL.

        This puts the same field on the screen where they now edit everything
        else about their page, and saves it through the very same method:
        `res.company.set_own_directory_category`, which resolves the company
        from the session, writes one field and refuses a folder category.
    """,
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Beta",
    "depends": [
        "partner_microsite_manager",
        "website_directory",
    ],
    "data": [
        "views/microsite_content_views.xml",
    ],
    "installable": True,
    # Same as the other directory bridges: whoever has both halves wants it.
    "auto_install": True,
}
