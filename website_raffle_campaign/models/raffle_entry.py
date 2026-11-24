# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

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
    merchant_id = fields.Many2one("res.company", required=True, ondelete="restrict")
    purchase_date = fields.Date(required=True)
    amount = fields.Float(digits=(16, 2), required=True)
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
            entry.receipt_url = (
                f"/web/content/{entry.receipt_attachment_id.id}?download=false"
                if entry.receipt_attachment_id
                else False
            )

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
            if entry.merchant_id not in entry.campaign_id.participating_company_ids:
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
            found |= self.search(
                [
                    ("campaign_id", "=", entry.campaign_id.id),
                    ("merchant_id", "=", entry.merchant_id.id),
                    ("purchase_date", "=", entry.purchase_date),
                    ("amount", "=", entry.amount),
                ]
            )
        return found | self

    def _refresh_duplicate_flags(self):
        """Recompute the hint for the whole group each entry belongs to.

        Stored plain (not a computed field) because adding an entry has to
        flag the EARLIER ones too, which no ``@api.depends`` on the new row
        can express.
        """
        for entry in self:
            group = self.search(
                [
                    ("campaign_id", "=", entry.campaign_id.id),
                    ("merchant_id", "=", entry.merchant_id.id),
                    ("purchase_date", "=", entry.purchase_date),
                    ("amount", "=", entry.amount),
                ]
            )
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

    def _anonymize(self):
        """Drop personal data and the receipt file; keep the audit skeleton."""
        self.mapped("receipt_attachment_id").sudo().unlink()
        self.write(
            {
                "participant_name": ANONYMIZED_NAME,
                "email": False,
                "phone": False,
                "submit_ip": False,
                "receipt_attachment_id": False,
                "anonymized": True,
            }
        )
