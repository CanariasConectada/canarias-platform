# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Website Directory - Company Facilities",
    "version": "19.0.1.0.0",
    "category": "Website",
    "summary": "Filter the business directory by the facilities a shop offers",
    "description": """
        "Instalaciones y servicios" stopped being a paragraph of free text and
        became a catalogue precisely so it could be READ by a filter. This is
        that filter: step-free access, card payment, parking nearby, we speak
        English -- ticked on the shop, chosen by the visitor in the directory.

        Several ticks narrow rather than widen: a visitor who asks for step-free
        access AND parking wants shops that have both, not shops that have
        either.
    """,
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Beta",
    "depends": [
        "company_facilities",
        "website_directory",
    ],
    "data": [
        "views/website_directory_templates.xml",
    ],
    "installable": True,
    # Same as the certification bridge: whoever has both halves wants the
    # bridge, and nobody has to be told a third module exists.
    "auto_install": True,
}
