# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Connect the platform's own verticals to the navigation of every site.

Measured 2026-08-02 and re-confirmed 2026-09-02: Memoria Viva, Lugares de
Interes and Resenas exist and answer 200, yet 215 of 218 sites linked none
of them -- the portal included, and Resenas was linked NOWHERE. From
19.0.2.1.0 a new microsite is born with the "Guia Local" dropdown; this
script gives it to the sites that predate the rule, reusing an existing
dropdown where one is already curated (the three zone sites) instead of
creating a twin next to it. It also restores the /comercio entry on the
sites that miss it: the directory cross-link is the estate standard the
homepage template already carries.

Create-only, per URL: an entry that exists anywhere in a site's menu --
whatever it was renamed to, wherever it was moved -- is left alone.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.auto_microsite_generator.models.res_company import (
        LOCAL_GUIDE_CHILDREN,
        LOCAL_GUIDE_MENU_LABELS,
        LOCAL_GUIDE_MENU_NAME,
        LOCAL_GUIDE_MENU_SEQUENCE,
        MENU_LABELS,
    )

    Menu = env["website.menu"].sudo()
    installed = {lang[0] for lang in env["res.lang"].get_installed()}

    def seed(menu, labels):
        for lang, label in labels.items():
            if lang in installed:
                menu.with_context(lang=lang).name = label

    guides_created = children_added = directories_added = 0
    for website in env["website"].search([]):
        root = Menu.search(
            [("website_id", "=", website.id), ("parent_id", "=", False)],
            limit=1,
        )
        if not root:
            continue

        # The directory cross-link, where it is missing (21 sites measured).
        if not Menu.search_count(
            [("website_id", "=", website.id), ("url", "=", "/comercio")]
        ):
            menu = Menu.create(
                {
                    "name": "Comercio",
                    "url": "/comercio",
                    "parent_id": root.id,
                    "sequence": 30,
                    "website_id": website.id,
                }
            )
            seed(menu, MENU_LABELS["/comercio"])
            directories_added += 1

        # The guide dropdown. Reuse the one a zone site already curates:
        # the parent of its Lugares entry, when that parent is a dropdown.
        missing = [
            (name, url, sequence)
            for name, url, sequence in LOCAL_GUIDE_CHILDREN
            if not Menu.search_count(
                [("website_id", "=", website.id), ("url", "=", url)]
            )
        ]
        if not missing:
            continue
        guide = Menu.browse()
        anchor = Menu.search(
            [
                ("website_id", "=", website.id),
                ("url", "=", "/explora/lugares-de-interes"),
            ],
            limit=1,
        )
        if anchor and anchor.parent_id and anchor.parent_id.url == "#":
            guide = anchor.parent_id
        if not guide:
            guide = Menu.create(
                {
                    "name": LOCAL_GUIDE_MENU_NAME,
                    "url": "#",
                    "parent_id": root.id,
                    "sequence": LOCAL_GUIDE_MENU_SEQUENCE,
                    "website_id": website.id,
                }
            )
            seed(guide, LOCAL_GUIDE_MENU_LABELS)
            guides_created += 1
        for name, url, sequence in missing:
            child = Menu.create(
                {
                    "name": name,
                    "url": url,
                    "parent_id": guide.id,
                    "sequence": sequence,
                    "website_id": website.id,
                }
            )
            if url in MENU_LABELS:
                seed(child, MENU_LABELS[url])
            children_added += 1

    _logger.info(
        "auto_microsite_generator: %s Guia Local dropdowns created, %s "
        "vertical entries added, %s /comercio entries restored.",
        guides_created, children_added, directories_added,
    )
