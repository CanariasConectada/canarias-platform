# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
import re

from lxml import etree

from odoo import models

_logger = logging.getLogger(__name__)

# The portal and the zone websites: their "/" is not a merchant homepage and
# has neither a contact section nor facilities of its own.
NON_MERCHANT_WEBSITE_IDS = (1, 12, 13, 14)

FACILITIES_CALL_MARKER = "company_facilities.facilities_block"

# ``website.company_id`` rather than a variable of the page: an imported
# homepage is plain builder HTML and knows nothing about whose shop it is.
FACILITIES_SNIPPET = (
    '<t t-set="cf_company" t-value="website.company_id.sudo()"/>'
    '<t t-call="company_facilities.facilities_block"/>\n'
)

CONTACT_SECTION_NAMES = ("Formulario", "Formulario Contacto")

# The opening tag of a contact section. Attribute values are matched as
# quoted strings so a ``>`` inside a ``style`` cannot end the tag early.
CONTACT_SECTION_RE = re.compile(
    r"<section(?:\s+[\w:.-]+(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'))?)*?"
    r"\s+data-name\s*=\s*\"(?:%s)\"" % "|".join(map(re.escape, CONTACT_SECTION_NAMES))
)

INSERTED = "inserted"
ALREADY_THERE = "already_there"
NO_CONTACT = "no_contact"
MALFORMED = "malformed"


def _parse(arch):
    """Parse an arch wrapped in a root, or return None when it is not XML."""
    try:
        return etree.fromstring("<cf_root>%s</cf_root>" % arch)
    except etree.XMLSyntaxError:
        return None


def insert_facilities_call(arch):
    """Put the facilities block right before the first contact section.

    Returns ``(new_arch, status)``. The arch is edited as text, not
    re-serialized through lxml, so every byte the builder and the translation
    terms rely on stays as it was; lxml only checks the result is still
    well-formed and that the call landed immediately before the section.
    """
    if FACILITIES_CALL_MARKER in arch:
        return arch, ALREADY_THERE
    if _parse(arch) is None:
        return arch, MALFORMED
    match = CONTACT_SECTION_RE.search(arch)
    if not match:
        return arch, NO_CONTACT
    new_arch = arch[: match.start()] + FACILITIES_SNIPPET + arch[match.start() :]
    tree = _parse(new_arch)
    if tree is None:
        return arch, MALFORMED
    call = tree.xpath("//t[@t-call='%s']" % FACILITIES_CALL_MARKER)
    following = call[0].getnext() if call else None
    if (
        following is None
        or following.tag != "section"
        or following.get("data-name") not in CONTACT_SECTION_NAMES
    ):
        return arch, MALFORMED
    return new_arch, INSERTED


class Website(models.Model):
    _inherit = "website"

    def _cf_place_facilities_in_homepage(self):
        """Call the facilities block before the contact section of homepages.

        The client wants every merchant homepage to end contact section ->
        funding strip -> footer (2026-09-16). The block used to hang off
        ``website.layout`` above ``div#footer``, which put it after the strip
        and inside the footer area; it now lives in the page itself.

        Scope: the ``/`` page of ``self`` (every website when empty), except
        the portal and zone websites and the homepages rendered by
        ``partner_microsite_manager.microsite_homepage_content``, which place
        the block themselves after the About section.

        Every language key of ``arch_db`` is edited, with raw SQL: a write
        under a language context would rewrite the other translations from
        the terms of one of them. A page is all-or-nothing: if one key is not
        well-formed XML the page is skipped and logged, so its languages never
        diverge. Idempotent: a key already calling the block is left alone.

        Returns a dict of counters: ``updated``, ``already_there``,
        ``skipped`` (malformed) and ``no_contact``.
        """
        websites = self or self.search([])
        pages = (
            self.env["website.page"]
            .sudo()
            .search(
                [
                    ("url", "=", "/"),
                    ("website_id", "in", websites.ids),
                    ("website_id", "not in", list(NON_MERCHANT_WEBSITE_IDS)),
                ]
            )
        )
        counts = dict(updated=0, already_there=0, skipped=0, no_contact=0)
        cr = self.env.cr
        views = pages.view_id
        views.flush_recordset(["arch_db"])
        for view in views:
            cr.execute("SELECT arch_db FROM ir_ui_view WHERE id = %s", (view.id,))
            archs = cr.fetchone()[0] or {}
            if any("microsite_homepage_content" in (a or "") for a in archs.values()):
                continue
            new_archs, statuses = {}, set()
            for lang, arch in archs.items():
                new_archs[lang], status = insert_facilities_call(arch or "")
                statuses.add(status)
            if MALFORMED in statuses:
                counts["skipped"] += 1
                _logger.warning(
                    "Facilities block: homepage view %s (website %s) is not "
                    "well-formed XML in some language; left untouched.",
                    view.id,
                    view.website_id.id,
                )
                continue
            if INSERTED not in statuses:
                key = ALREADY_THERE if ALREADY_THERE in statuses else "no_contact"
                counts[key] += 1
                if key == "no_contact":
                    _logger.info(
                        "Facilities block: homepage view %s (website %s) has "
                        "no contact section; left untouched.",
                        view.id,
                        view.website_id.id,
                    )
                continue
            cr.execute(
                "UPDATE ir_ui_view SET arch_db = %s::jsonb WHERE id = %s",
                (json.dumps(new_archs), view.id),
            )
            counts["updated"] += 1
        if counts["updated"]:
            views.invalidate_recordset(["arch_db"])
            self.env.registry.clear_cache("templates")
        return counts
