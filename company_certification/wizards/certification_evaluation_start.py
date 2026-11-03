# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CertificationEvaluationStart(models.TransientModel):
    """Ask which seal before starting an evaluation.

    Consolidating the two "Mis Evaluaciones" menus into one list took the two
    "Nueva Evaluación" entries with them, and each of those carried the answer
    to a question the merged list never asks: WHICH seal. The list came out
    tidier and the platform stopped being able to start an evaluation at all.

    So the question moves here. One entry point for every seal, and the first
    thing it asks is the thing the per-seal menus used to answer by the route
    you took to reach them.
    """

    _name = "certification.evaluation.start"
    _description = "Start a certification evaluation"

    certification_type_id = fields.Many2one(
        comodel_name="certification.type",
        string="Seal",
        required=True,
        help="Which seal you want to work towards.",
    )
    available_type_ids = fields.Many2many(
        comodel_name="certification.type",
        string="Seals available to you",
        compute="_compute_available_type_ids",
        help="Technical: the domain of the seal field.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Shop",
        readonly=True,
        default=lambda self: self.env.user.company_id,
        help="The shop the seal would belong to. It is the active company of "
        "your own account and cannot be chosen here.",
    )
    blocker = fields.Char(
        string="Why not",
        compute="_compute_blocker",
        help="What stands between this shop and this evaluation right now, "
        "in the merchant's own words.",
    )

    @api.depends_context("uid")
    def _compute_available_type_ids(self):
        """Only the seals this account is entitled to run.

        The same group ``_start_certification_evaluation`` enforces, asked
        here as well: a picker that offers a seal only to refuse it after the
        click is a worse version of no picker at all. The check downstream is
        the one that protects the data; this one protects the afternoon.
        """
        groups = self.env.user.all_group_ids
        types = self.env["certification.type"].sudo().search([])
        allowed = types.filtered(
            lambda cert_type: not cert_type.group_user_id
            or cert_type.group_user_id in groups
        )
        for wizard in self:
            wizard.available_type_ids = allowed

    @api.depends("certification_type_id", "company_id")
    def _compute_blocker(self):
        """Say no before the click, not after it.

        ``_start_certification_evaluation`` raises for three reasons. All
        three are knowable the moment the seal is picked, and a merchant who
        reads "you cannot run a new evaluation until 12/11/2026" while the
        dialog is still open has been told something useful; the same
        sentence as a red error box after pressing Start reads like a
        failure of the platform.
        """
        for wizard in self:
            wizard.blocker = wizard._blocker_message()

    def _blocker_message(self):
        self.ensure_one()
        cert_type = self.certification_type_id.sudo()
        if not cert_type:
            return False
        if not self.company_id:
            return _("Your user profile has no shop, so there is nothing to certify.")
        if not cert_type.survey_id or not cert_type.survey_id.active:
            return _(
                "%s has no questionnaire configured yet. Please contact the "
                "administrator.",
                cert_type.name,
            )
        last = (
            self.env["survey.user_input"]
            .sudo()
            ._get_last_done_attempt(cert_type, self.company_id)
        )
        if (
            last
            and last.next_attempt_date
            and last.next_attempt_date > fields.Date.today()
        ):
            return _(
                "This shop already sat the %(seal)s evaluation. The next "
                "attempt may be made from %(date)s.",
                seal=cert_type.name,
                date=last.next_attempt_date,
            )
        return False

    def action_start(self):
        """Open the questionnaire, or explain why it cannot be opened.

        The authorisation, the missing questionnaire and the cooldown are all
        re-checked by ``_start_certification_evaluation``: this wizard is a
        convenience over a public model method, never the thing that decides.
        """
        self.ensure_one()
        blocker = self._blocker_message()
        if blocker:
            raise UserError(blocker)
        return self.env["survey.user_input"].action_start_certification(
            self.certification_type_id.id
        )
