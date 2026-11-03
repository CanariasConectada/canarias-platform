# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Helpers shared by the microsite tests of this module and of its bridges."""

import re


def render_homepage_for(env, company):
    """Give the company a website of its own and render its dynamic homepage.

    Returns the HTML as a string. The bridges reuse it to assert what the
    cover shows once their part of the chain is installed.
    """
    website = env["website"].create(
        {"name": "%s site" % company.name, "company_id": company.id}
    )
    company.website_id = website
    return str(
        env["ir.qweb"]._render(
            "partner_microsite_manager.microsite_homepage_content",
            {"website": website},
        )
    )


def hero_h1_pattern(title):
    """Regex matching the hero H1 carrying exactly ``title``."""
    return r"<h1[^>]*>\s*%s\s*</h1>" % re.escape(title)
