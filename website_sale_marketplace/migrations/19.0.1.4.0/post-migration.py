# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Unlink the marketplace company from products of retired merchants.

The backfill used to link the portal's marketplace company to every product
with an owner, archived merchants included, so the aggregated shop kept
advertising catalogues of businesses that had left the platform. The sync is
filtered from this version on; this cleans up the links it already wrote.

Pure SQL on the m2m table: no recomputation is wanted here — touching
``company_ids`` through the ORM recomputes delivery carriers, and 68
businesses without a pickup carrier of their own make that blow up (the same
reason the backfill batches and the zone shops skip it entirely).
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        WITH marketplace AS (
            -- Same set _marketplace_companies() resolves: the owners of
            -- EVERY marketplace website, zones included, so a zone company
            -- in company_ids never counts as a product's "real" owner.
            SELECT DISTINCT company_id
            FROM website
            WHERE is_marketplace
        ),
        portal AS (
            SELECT DISTINCT company_id
            FROM website
            WHERE is_marketplace AND (marketplace_zone IS NULL OR marketplace_zone = '')
        ),
        doomed AS (
            SELECT r.product_template_id, r.res_company_id
            FROM product_template_res_company_rel r
            JOIN portal p ON p.company_id = r.res_company_id
            WHERE NOT EXISTS (
                SELECT 1
                FROM product_template_res_company_rel r2
                JOIN res_company c2 ON c2.id = r2.res_company_id
                WHERE r2.product_template_id = r.product_template_id
                  AND c2.active
                  AND c2.id NOT IN (SELECT company_id FROM marketplace)
            )
        )
        DELETE FROM product_template_res_company_rel r
        USING doomed d
        WHERE r.product_template_id = d.product_template_id
          AND r.res_company_id = d.res_company_id
        """
    )
    _logger.info(
        "Marketplace links removed from %s product(s) of retired merchants",
        cr.rowcount,
    )
