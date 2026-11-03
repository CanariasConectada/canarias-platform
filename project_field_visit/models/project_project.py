# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import copy

from odoo import Command, _, api, fields, models

from .project_task import MANAGER_GROUP

YES_NO_PENDING = [["yes", "Sí"], ["no", "No"], ["pending", "Pendiente"]]

PARTICIPATION_STATUS = [
    ["yes", "Sí"],
    ["pending", "Pendiente"],
    ["no", "No"],
    ["new", "Nueva adhesión"],
    ["new_pending", "Nueva adhesión / pendiente"],
    ["prospect", "Posible adhesión"],
    ["closed", "Cerrado"],
    ["withdrawn", "No quiere continuar"],
]

# The checklist of the first phase, as the client keeps it in the
# spreadsheet. It is DATA of one project, not code: labels are what the
# consultants read (Spanish, the working language of the programme), and the
# next phase defines its own fields on its own project from the interface.
PHASE_ONE_PROPERTIES = [
    {"name": "annex_number", "string": "Anexo", "type": "integer"},
    {"name": "microsite", "string": "Microsite", "type": "boolean"},
    {
        "name": "justified_list",
        "string": "Justificados en listado Fase I",
        "type": "selection",
        "selection": YES_NO_PENDING,
    },
    {
        "name": "graphic_evidence",
        "string": "Evidencias gráficas Fase I",
        "type": "selection",
        "selection": YES_NO_PENDING,
    },
    {
        "name": "commitment_signed",
        "string": "Compromisos firmados",
        "type": "selection",
        "selection": YES_NO_PENDING,
    },
    {
        "name": "participation_status",
        "string": "Estado participación",
        "type": "selection",
        "selection": PARTICIPATION_STATUS,
    },
    {
        "name": "training",
        "string": "Formación",
        "type": "selection",
        "selection": YES_NO_PENDING,
    },
    {
        "name": "declaration_signed",
        "string": "Declaración firmada",
        "type": "selection",
        "selection": YES_NO_PENDING,
    },
]


class ProjectProject(models.Model):
    _inherit = "project.project"

    is_field_visit_project = fields.Boolean(
        string="Door-to-door field visits",
        help="Tasks of this project are visits to the businesses of the "
        "platform: each task is linked to the visited business and its "
        "microsite, and consultants log their visits from the task.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        if any(vals.get("is_field_visit_project") for vals in vals_list):
            self.env["project.task"]._check_field_visit_access(MANAGER_GROUP)
        return super().create(vals_list)

    def write(self, vals):
        if "is_field_visit_project" in vals:
            self.env["project.task"]._check_field_visit_access(MANAGER_GROUP)
        return super().write(vals)

    def _field_visit_phase_one_properties(self):
        """Checklist definition proposed for a phase that has none yet."""
        return [
            dict(copy.deepcopy(prop), view_in_cards=True)
            for prop in PHASE_ONE_PROPERTIES
        ]

    def _field_visit_ensure_properties(self):
        """Give the project the phase-one checklist when it has no fields.

        A project that already defines its own task properties is left
        alone: those are the fields of its phase.
        """
        for project in self:
            if not project.task_properties_definition:
                project.task_properties_definition = (
                    project._field_visit_phase_one_properties()
                )

    @api.model
    def _field_visit_grant_admins(self):
        """Give the platform administrators the *Field visit manager* access.

        Runs once, at install or at the upgrade to 19.0.1.2.0, and only while
        nobody has been appointed yet (the built-in superuser and admin get
        the group from the module itself): once someone runs the programme,
        who is a manager is their decision, never the module's.
        """
        group = self.env.ref(MANAGER_GROUP, raise_if_not_found=False)
        if not group:
            return self.env["res.users"]
        group = group.sudo()
        builtin = self.env.ref("base.user_root") | self.env.ref(
            "base.user_admin", raise_if_not_found=False
        )
        appointed = group.with_context(active_test=False).user_ids - builtin
        if appointed.filtered(lambda u: u.active and not u.share):
            return self.env["res.users"]
        admins = (
            self.env.ref("base.group_system")
            .sudo()
            .all_user_ids.filtered(lambda u: u.active and not u.share)
        ) - group.user_ids
        if admins:
            group.write({"user_ids": [Command.link(user.id) for user in admins]})
        return admins

    def action_open_field_visit_import(self):
        self.ensure_one()
        self.env["project.task"]._check_field_visit_access(MANAGER_GROUP)
        return {
            "type": "ir.actions.act_window",
            "name": _("Import field visits"),
            "res_model": "project.field.visit.import",
            "view_mode": "form",
            "target": "new",
            "context": {"default_project_id": self.id},
        }
