# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
import re

from lxml import etree

from odoo import models

_logger = logging.getLogger(__name__)

# The portal and the zone websites: their "/" is not a merchant homepage and
# has no contact section to anchor on. They keep the layout-level render.
NON_MERCHANT_WEBSITE_IDS = (1, 12, 13, 14)

SEALS_CALL_MARKER = "company_certification.certification_block"

# ``website.company_id`` rather than a variable of the page: an imported
# homepage is plain builder HTML and knows nothing about whose shop it is.
# The trailing newline keeps the call on its own line in the arch.
SEALS_SNIPPET = (
    '<t t-set="cc_company" t-value="website.company_id"/>'
    '<t t-call="company_certification.certification_block"/>\n'
)

# Homepages rendered from this template are not edited: the template places
# the seals itself (see ``_cc_dynamic_homepage_places_seals``).
DYNAMIC_HOMEPAGE_MARKER = "partner_microsite_manager.microsite_homepage_content"

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
        return etree.fromstring("<cc_root>%s</cc_root>" % arch)
    except etree.XMLSyntaxError:
        return None


def insert_seals_call(arch):
    """Put the seals block right before the first contact section.

    ``company_facilities`` anchors its own call on the same section, and its
    call is already in the imported homepages, so "right before the contact
    section" is also "right after the facilities": the page reads facilities,
    seals, contact. No dependency between the two modules is needed for it.

    Returns ``(new_arch, status)``. The arch is edited as text, not
    re-serialized through lxml, so every byte the builder and the translation
    terms rely on stays as it was; lxml only checks the result is still
    well-formed and that the call landed immediately before the section.
    """
    if SEALS_CALL_MARKER in arch:
        return arch, ALREADY_THERE
    if _parse(arch) is None:
        return arch, MALFORMED
    match = CONTACT_SECTION_RE.search(arch)
    if not match:
        return arch, NO_CONTACT
    new_arch = arch[: match.start()] + SEALS_SNIPPET + arch[match.start() :]
    tree = _parse(new_arch)
    if tree is None:
        return arch, MALFORMED
    call = tree.xpath("//t[@t-call='%s']" % SEALS_CALL_MARKER)
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

    def _cc_dynamic_homepage_places_seals(self):
        """Whether the dynamic microsite homepage template calls the block.

        ``partner_microsite_manager`` is not a dependency of this module (nor
        the other way round): its homepage template asks this module for the
        block through ``_pmm_certification_block_template``. An installation
        whose ``partner_microsite_manager`` predates that hook keeps the
        layout-level render, so the seals never vanish from a homepage.
        """
        return hasattr(self, "_pmm_certification_block_template")

    def _cc_page_places_seals(self, main_object=None):
        """Whether the page being rendered shows the seals block itself.

        The layout-level section stays silent on such a page, so the seals
        never show twice. Cheap on purpose, the layout calls this once per
        homepage view: it reads ``arch_db`` of the page's own view, a row the
        ORM has already fetched to render the page. Read with ``lang=None``
        (the ``en_US`` base value): the marker lives in a ``t-call``
        attribute, which ``xml_translate`` never translates, and
        ``_cc_place_seals_in_homepage`` writes it in every language at once.
        """
        view = None
        name = getattr(main_object, "_name", None)
        if name == "website.page":
            view = main_object.sudo().view_id
        elif name == "ir.ui.view":
            view = main_object.sudo()
        if not view:
            return False
        arch = view.with_context(lang=None).arch_db or ""
        if SEALS_CALL_MARKER in arch:
            return True
        return (
            DYNAMIC_HOMEPAGE_MARKER in arch and self._cc_dynamic_homepage_places_seals()
        )

    def _cc_place_seals_in_homepage(self):
        """Call the seals block before the contact section of homepages.

        The client wants every merchant homepage to end facilities, seals,
        contact section, funding strip, footer (2026-09-21). The seals hung
        off ``website.layout`` above ``footer#bottom``, which put them after
        the funding strip; on merchant homepages they now live in the page.

        Scope: the ``/`` page of ``self`` (every website when empty), except
        the portal and zone websites and the homepages rendered by
        ``partner_microsite_manager.microsite_homepage_content``, whose
        template places the block itself.

        Every language key of ``arch_db`` is edited, with raw SQL: a write
        under a language context would rewrite the other translations from
        the terms of one of them. A page is all-or-nothing: if one key is not
        well-formed XML, or has no contact section, the page is skipped and
        logged, so its languages never diverge. Idempotent: a key already
        calling the block is left alone.

        Returns a dict of counters: ``updated``, ``already_there``,
        ``skipped`` (malformed), ``no_contact`` and ``dynamic``.
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
        counts = dict(updated=0, already_there=0, skipped=0, no_contact=0, dynamic=0)
        cr = self.env.cr
        views = pages.view_id
        views.flush_recordset(["arch_db"])
        for view in views:
            cr.execute("SELECT arch_db FROM ir_ui_view WHERE id = %s", (view.id,))
            archs = cr.fetchone()[0] or {}
            if any(DYNAMIC_HOMEPAGE_MARKER in (a or "") for a in archs.values()):
                counts["dynamic"] += 1
                continue
            new_archs, statuses = {}, set()
            for lang, arch in archs.items():
                new_archs[lang], status = insert_seals_call(arch or "")
                statuses.add(status)
            if MALFORMED in statuses:
                counts["skipped"] += 1
                _logger.warning(
                    "Certification seals: homepage view %s (website %s) is not "
                    "well-formed XML in some language; left untouched.",
                    view.id,
                    view.website_id.id,
                )
                continue
            if NO_CONTACT in statuses:
                # Also when only some languages lack the section: the layout
                # reads one language to know whether the page has the block.
                counts["no_contact"] += 1
                _logger.info(
                    "Certification seals: homepage view %s (website %s) has "
                    "no contact section in some language; left untouched.",
                    view.id,
                    view.website_id.id,
                )
                continue
            if INSERTED not in statuses:
                counts["already_there"] += 1
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
