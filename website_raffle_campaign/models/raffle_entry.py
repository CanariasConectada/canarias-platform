# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

ANONYMIZED_NAME = "[anonymized]"


class RaffleEntry(models.Model):
    """One registered receipt. Never a ``res.partner``: a shopper who typed
    a name into a raffle form is not a contact of any merchant."""

    _name = "raffle.entry"
    _description = "Raffle Entry"
    _inherit = ["mail.thread"]
    _order = "id desc"
    _rec_name = "reference"

    campaign_id = fields.Many2one(
        "raffle.campaign", required=True, ondelete="cascade", index=True
    )
    reference = fields.Char(readonly=True, copy=False, index=True, default="/")
    # Participant data. Required in practice (see ``_check_participant``), but
    # not NOT NULL in the database because anonymization has to blank them.
    participant_name = fields.Char()
    email = fields.Char(index=True)
    phone = fields.Char()
    # Named ``merchant_id`` and not ``company_id`` on purpose: a field called
    # ``company_id`` makes other modules of this platform treat the record as
    # company-owned and filter it by the user's companies.
    # Empty when the campaign does not ask for the merchant.
    merchant_id = fields.Many2one("res.company", ondelete="restrict")
    purchase_date = fields.Date(required=True)
    # 0 when the campaign does not ask for the amount.
    amount = fields.Float(digits=(16, 2))
    ask_merchant = fields.Boolean(related="campaign_id.ask_merchant")
    ask_amount = fields.Boolean(related="campaign_id.ask_amount")
    amount_label = fields.Char(compute="_compute_amount_label")
    receipt_attachment_id = fields.Many2one(
        "ir.attachment", copy=False, ondelete="set null", readonly=True
    )
    receipt_image = fields.Image(
        compute="_compute_receipt_image", max_width=1024, max_height=1024
    )
    receipt_url = fields.Char(compute="_compute_receipt_url")
    receipt_checksum = fields.Char(readonly=True, copy=False, index=True)
    possible_duplicate = fields.Boolean(
        readonly=True,
        copy=False,
        help="Same merchant, date and amount as another entry of the campaign. "
        "Only a hint for the reviewer: it never blocks the entry.",
    )
    # Consent
    is_adult = fields.Boolean(readonly=True)
    terms_accepted = fields.Boolean(readonly=True)
    terms_accepted_at = fields.Datetime(readonly=True)
    terms_version = fields.Char(readonly=True)
    # Review
    state = fields.Selection(
        [("pending", "Pending"), ("valid", "Valid"), ("rejected", "Rejected")],
        default="pending",
        required=True,
        index=True,
        tracking=True,
        copy=False,
    )
    reject_reason = fields.Char(tracking=True)
    submit_ip = fields.Char(readonly=True, copy=False)
    anonymized = fields.Boolean(readonly=True, copy=False)
    # 1 = winner, 2.. = alternates in order, 0 = not drawn
    draw_rank = fields.Integer(readonly=True, copy=False)

    _checksum_per_campaign = models.Constraint(
        "UNIQUE (campaign_id, receipt_checksum)",
        "This receipt is already registered in the campaign.",
    )

    # ------------------------------------------------------------------
    @api.depends("amount", "campaign_id.ask_amount")
    def _compute_amount_label(self):
        for entry in self:
            entry.amount_label = (
                f"{entry.amount:.2f}" if entry.campaign_id.ask_amount else "—"
            )

    @api.depends("receipt_attachment_id")
    def _compute_receipt_image(self):
        for entry in self:
            attachment = entry.receipt_attachment_id.sudo()
            if attachment and attachment.mimetype in (
                "image/jpeg",
                "image/png",
                "image/webp",
            ):
                entry.receipt_image = attachment.datas
            else:
                entry.receipt_image = False

    @api.depends("receipt_attachment_id")
    def _compute_receipt_url(self):
        for entry in self:
            attachment = entry.receipt_attachment_id
            if not attachment:
                entry.receipt_url = False
                continue
            # Only images are safe to show inline; PDF and HEIC download.
            inline = attachment.mimetype in ("image/jpeg", "image/png", "image/webp")
            flag = "false" if inline else "true"
            entry.receipt_url = f"/web/content/{attachment.id}?download={flag}"

    @api.constrains("participant_name", "email", "phone", "anonymized")
    def _check_participant(self):
        for entry in self:
            if entry.anonymized:
                continue
            if not (entry.participant_name and entry.email and entry.phone):
                raise ValidationError(_("Name, email and phone are required."))

    @api.constrains("merchant_id", "campaign_id")
    def _check_merchant(self):
        for entry in self:
            campaign = entry.campaign_id
            if not campaign.ask_merchant:
                continue
            if entry.merchant_id not in campaign.participating_company_ids:
                raise ValidationError(
                    _("The merchant does not take part in this campaign.")
                )

    @api.constrains("is_adult", "terms_accepted", "anonymized")
    def _check_consent(self):
        for entry in self:
            if not entry.anonymized and not (entry.is_adult and entry.terms_accepted):
                raise ValidationError(_("Both consent boxes must be ticked."))

    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("reference") or vals["reference"] == "/":
                vals["reference"] = self.env["ir.sequence"].next_by_code("raffle.entry")
        entries = super().create(vals_list)
        entries._refresh_duplicate_flags()
        return entries

    def write(self, vals):
        keys = {"campaign_id", "merchant_id", "purchase_date", "amount"}
        if (keys | {"state"}) & set(vals) and self.filtered(
            lambda e: e.campaign_id.state == "drawn"
        ):
            raise UserError(
                _("The draw is done: reset it before editing the entries' review.")
            )
        touched = bool(keys & set(vals))
        before = self._duplicate_groups() if touched else self.browse()
        result = super().write(vals)
        if touched:
            (before | self)._refresh_duplicate_flags()
        return result

    def _duplicate_groups(self):
        """Every entry sharing a (campaign, merchant, date, amount) key with self."""
        found = self.browse()
        for entry in self:
            found |= self.search(entry._duplicate_domain())
        return found | self

    def _duplicate_domain(self):
        """Key of a possible duplicate: date, plus the merchant and the amount
        when the campaign asks for them. With neither there is nothing to
        compare, so the domain matches the entry alone."""
        self.ensure_one()
        campaign = self.campaign_id
        if not (campaign.ask_merchant or campaign.ask_amount):
            return [("id", "=", self.id)]
        domain = [
            ("campaign_id", "=", campaign.id),
            ("purchase_date", "=", self.purchase_date),
        ]
        if campaign.ask_merchant:
            domain.append(("merchant_id", "=", self.merchant_id.id))
        if campaign.ask_amount:
            domain.append(("amount", "=", self.amount))
        return domain

    def _refresh_duplicate_flags(self):
        """Recompute the hint for the whole group each entry belongs to.

        Stored plain (not a computed field) because adding an entry has to
        flag the EARLIER ones too, which no ``@api.depends`` on the new row
        can express.
        """
        for entry in self:
            group = self.search(entry._duplicate_domain())
            flag = len(group) > 1
            todo = group.filtered(lambda e, flag=flag: e.possible_duplicate != flag)
            if todo:
                super(RaffleEntry, todo).write({"possible_duplicate": flag})

    # ------------------------------------------------------------------
    def action_validate(self):
        self.write({"state": "valid", "reject_reason": False})

    def action_reset_pending(self):
        self.write({"state": "pending", "reject_reason": False})

    def action_reject_wizard(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": "raffle.entry.reject.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_entry_ids": self.ids},
        }

    def unlink(self):
        if self.filtered(lambda e: e.campaign_id.state == "drawn"):
            raise UserError(_("The draw is done: entries cannot be deleted."))
        return super().unlink()

    def _anonymize(self):
        """Drop personal data, receipt file and chatter; keep the skeleton."""
        self.mapped("receipt_attachment_id").sudo().unlink()
        # tracking_disable: the wipe itself must not write a new tracking line
        # holding the old reject reason.
        self.with_context(tracking_disable=True).write(
            {
                "reject_reason": False,
                "participant_name": ANONYMIZED_NAME,
                "email": False,
                "phone": False,
                "submit_ip": False,
                "receipt_attachment_id": False,
                "anonymized": True,
            }
        )
        # Earlier tracking lines (state, reject reason) go with their messages.
        self.env["mail.message"].sudo().search(
            [("model", "=", "raffle.entry"), ("res_id", "in", self.ids)]
        ).unlink()
