# Copyright 2026 Canarias Conectada
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

import json
import logging

from odoo import fields, models
from odoo.tools import format_amount

_logger = logging.getLogger(__name__)

DEFAULT_PUSH_ICON = "/web/static/img/odoo-icon-192x192.png"


class SaleOrder(models.Model):
    _inherit = "sale.order"

    merchant_alert_sent = fields.Boolean(
        copy=False,
        readonly=True,
        help="Technical: the shop was already told about this website order, "
        "so neither a later confirmation nor a payment update alerts it again.",
    )

    def _action_confirm(self):
        result = super()._action_confirm()
        self._merchant_alert_once()
        return result

    def _merchant_alert_once(self):
        """Alert the shop about each website order, at most once per order.

        Called from every point where a customer completes a checkout: the
        order confirmation and the payment post-processing (for a provider
        that leaves the order unconfirmed, like a wire transfer). The flag is
        what keeps an on-site payment, which goes through both, from alerting
        twice.
        """
        for order in self.filtered(
            lambda o: o.website_id and not o.merchant_alert_sent
        ):
            order.sudo().merchant_alert_sent = True
            try:
                with self.env.cr.savepoint():
                    order._merchant_alert()
            except Exception:  # noqa: BLE001 - never break a checkout for a mail
                _logger.exception(
                    "Merchant alert failed for %s; the order stands.", order.name
                )

    def _merchant_alert_recipients(self):
        """Internal users who work for the order's shop.

        A merchant often has the shop as an allowed company rather than as
        the main one, so both count. Platform administrators are allowed in
        every shop: they are only alerted about the shop that is their main
        company, or every order of every shop would reach them.
        """
        self.ensure_one()
        company = self.company_id
        users = (
            self.env["res.users"]
            .sudo()
            .search(
                [
                    ("share", "=", False),
                    ("active", "=", True),
                    "|",
                    ("company_id", "=", company.id),
                    ("company_ids", "in", company.ids),
                ]
            )
        )
        return users.filtered(
            lambda u: u.company_id == company or not u.has_group("base.group_system")
        )

    def _merchant_alert(self):
        """Tell the shop somebody just bought from their website.

        Website orders here carry no salesperson and no followers: the
        platform confirms them, not a human, so nobody would ever hear
        about them. The shop's internal users are subscribed so the
        order shows in their chatter, the company mailbox gets an
        explicit template mail because a follower subscription alone
        sends nothing for a message that was already posted, and every
        device those users registered for notifications gets a web push.
        """
        self.ensure_one()
        staff = self._merchant_alert_recipients()
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
        try:
            with self.env.cr.savepoint():
                self._merchant_alert_push(staff.partner_id)
        except Exception:  # noqa: BLE001 - the mail above must still go out
            _logger.exception(
                "Merchant push failed for %s; the order and its mail stand.",
                self.name,
            )

    def _merchant_alert_push(self, partners):
        """Queue a web push to every device of ``partners``.

        Core only pushes a chatter message to partners notified in the
        inbox, and merchants are notified by email, so the push is sent
        here directly. It is always QUEUED as ``mail.push`` rows and handed
        to core's push cron, never sent inline: the rows roll back with an
        order whose transaction fails, so a customer never triggers a push
        for an order that does not exist, and the checkout request does not
        wait on the push services. Core does the same beyond a handful of
        devices; ``_trigger`` only wakes the cron after the commit.
        """
        self.ensure_one()
        devices, private_key, public_key = self._web_push_get_partners_parameters(
            partners.ids
        )
        if not devices or not private_key or not public_key:
            return
        payload_by_lang = {}
        for lang in set(devices.partner_id.mapped("lang")):
            payload_by_lang[lang] = json.dumps(
                self._web_push_truncate_payload(
                    self.with_context(
                        lang=lang or self.company_id.partner_id.lang or None
                    )._merchant_alert_push_payload()
                )
            )
        self.env["mail.push"].sudo().create(
            [
                {
                    "mail_push_device_id": device.id,
                    "payload": payload_by_lang[device.partner_id.lang],
                }
                for device in devices
            ]
        )
        self.env.ref("mail.ir_cron_web_push_notification")._trigger()

    def _merchant_alert_push_icon(self):
        website = self.website_id.sudo()
        if website.logo:
            return f"/web/image/website/{website.id}/logo/192x192"
        company = self.company_id.sudo()
        if company.logo:
            return f"/web/image/res.company/{company.id}/logo/192x192"
        return DEFAULT_PUSH_ICON

    def _merchant_alert_push_payload(self):
        """Notification for the language of ``self.env``."""
        self.ensure_one()
        order = self.sudo()
        env = self.env
        body = " · ".join(
            part
            for part in (
                order.company_id.name,
                format_amount(env, order.amount_total, order.currency_id),
                order.partner_id.name,
            )
            if part
        )
        action_path = "orders" if order.state == "sale" else "sales"
        return {
            "title": env._("New order %(name)s", name=order.name),
            "options": {
                "body": body,
                "icon": self._merchant_alert_push_icon(),
                "tag": f"order-{order.id}",
                "renotify": True,
                "silent": False,
                "requireInteraction": False,
                "data": {
                    # Core's backend worker opens /odoo/<model>/<res_id>;
                    # the website app worker prefers a same-origin url.
                    "model": "sale.order",
                    "res_id": order.id,
                    "url": f"/odoo/{action_path}/{order.id}",
                },
            },
        }
