# Copyright 2026 Canarias Conectada
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _action_confirm(self):
        result = super()._action_confirm()
        for order in self.filtered("website_id"):
            try:
                order._merchant_alert()
            except Exception:  # noqa: BLE001 - never break a checkout for a mail
                _logger.exception(
                    "Merchant alert failed for %s; the order stands.", order.name
                )
        return result

    def _merchant_alert(self):
        """Tell the shop somebody just bought from their website.

        Website orders here carry no salesperson and no followers: the
        platform confirms them, not a human, so nobody would ever hear
        about them. The company's internal users are subscribed so the
        order shows in their chatter, and the company mailbox gets an
        explicit template mail because a follower subscription alone
        sends nothing for a message that was already posted.
        """
        self.ensure_one()
        staff = self.env["res.users"].sudo().search(
            [
                ("share", "=", False),
                ("company_id", "=", self.company_id.id),
                ("active", "=", True),
            ]
        )
        partners = staff.partner_id.filtered("email")
        if partners:
            self.message_subscribe(partner_ids=partners.ids)
        template = self.env.ref(
            "website_sale_merchant_alert.mail_template_merchant_alert",
            raise_if_not_found=False,
        )
        recipient = self.company_id.partner_id.email or (
            partners[:1].email if partners else False
        )
        if template and recipient:
            # email_values, not context: send_mail does not carry the
            # context into field rendering, and an empty email_to falls
            # back to the record's default recipients - the buyer.
            template.sudo().send_mail(
                self.id,
                email_values={"email_to": recipient},
                email_layout_xmlid="mail.mail_notification_light",
            )
