# Copyright 2026 Canarias Conectada
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import models


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    def _post_process(self):
        """Alert the shop when a checkout ends without a confirmation.

        Every provider enabled on the platform confirms the order when the
        customer completes the checkout (pay on site, cash on delivery, a
        zero-amount cart), and the alert goes out from the confirmation. A
        provider that leaves the order as a quotation - a wire transfer, a
        card payment still pending - only reaches this point: the customer
        is done, so the shop hears about the order now. The alert flag on
        the order keeps a transaction that also confirms from alerting twice.
        """
        result = super()._post_process()
        finished = self.filtered(
            lambda tx: tx.operation != "validation"
            and tx.state in ("pending", "authorized", "done")
        )
        finished.sale_order_ids._merchant_alert_once()
        return result
