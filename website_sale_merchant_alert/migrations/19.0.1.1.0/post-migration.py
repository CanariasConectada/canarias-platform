# Copyright 2026 Canarias Conectada
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html


def migrate(cr, version):
    """Website orders confirmed before the flag existed were already alerted.

    Without this, cancelling one and confirming it again would alert the
    shop a second time.
    """
    cr.execute(
        """
        UPDATE sale_order
           SET merchant_alert_sent = TRUE
         WHERE website_id IS NOT NULL
           AND state = 'sale'
        """
    )
