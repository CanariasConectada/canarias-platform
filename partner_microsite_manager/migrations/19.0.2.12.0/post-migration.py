# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Convert every stored map link to a URL Google lets us frame.

    Share links (``maps.app.goo.gl``, ``/maps/place/...``) answer with
    ``X-Frame-Options: SAMEORIGIN`` and HTML-escaped embed URLs (``&amp;``
    copied from an iframe source) reach Google as broken parameters, so the
    microsite map showed the browser's error page. Short links are resolved
    over the network, one savepoint per company; a failure leaves the value
    as it was and the render falls back to the address map. Idempotent.
    """
    if not version:
        return
    # The help text of the map field changed. Its old translations would
    # survive the update (a .po never overwrites an existing value), so they
    # are dropped here: post-migrations run before the module's .po files
    # are loaded, which then fill in the new wording.
    cr.execute(
        """
        UPDATE ir_model_fields
           SET help = jsonb_build_object('en_US', help->>'en_US')
         WHERE model = 'res.company' AND name = 'microsite_map_url'
           AND help IS NOT NULL
        """
    )
    env = api.Environment(cr, SUPERUSER_ID, {})
    companies = (
        env["res.company"]
        .with_context(active_test=False)
        .search([("microsite_map_url", "!=", False)])
    )
    changed = companies._normalize_existing_map_urls()
    _logger.info(
        "Map links: %d companies carry one, %d converted to an embeddable URL "
        "(ids %s).",
        len(companies),
        len(changed),
        changed.ids,
    )
