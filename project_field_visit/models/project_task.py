# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

VISIT_OUTCOMES = [
    ("visited", "Visited, spoke with the business"),
    ("documents", "Documents collected or signed"),
    ("appointment", "Appointment scheduled"),
    ("absent", "Nobody available, come back later"),
    ("refused", "Does not want to continue"),
    ("closed", "Business closed"),
    ("other", "Other"),
]


class ProjectTask(models.Model):
    _inherit = "project.task"

    is_field_visit_project = fields.Boolean(related="project_id.is_field_visit_project")
    # The VISITED business. Not ``company_id``: that one is the company that
    # owns the task (the programme), and the visited business is usually
    # outside the consultant's allowed companies. Hence no ``check_company``
    # and the stored ``business_name`` / ``business_microsite_url`` below:
    # a consultant reads the task without ever reading the business records.
    business_company_id = fields.Many2one(
        "res.company",
        string="Visited business",
        index="btree_not_null",
        ondelete="set null",
        tracking=True,
        help="Business of the platform this task documents.",
    )
    business_partner_id = fields.Many2one(
        "res.partner",
        string="Business contact",
        compute="_compute_business_partner_id",
        store=True,
        readonly=False,
        index="btree_not_null",
        ondelete="set null",
        tracking=True,
        help="Contact of the visited business. For a business that is not on "
        "the platform yet (a prospect) this is the only link.",
    )
    business_website_id = fields.Many2one(
        "website",
        string="Microsite",
        compute="_compute_business_website_id",
        store=True,
        readonly=False,
        ondelete="set null",
    )
    business_name = fields.Char(
        compute="_compute_business_name",
        store=True,
        string="Business",
    )
    business_microsite_url = fields.Char(
        compute="_compute_business_microsite_url",
        store=True,
        string="Microsite URL",
    )
    field_visit_last_date = fields.Datetime(
        string="Last visit", readonly=True, copy=False
    )
    field_visit_last_outcome = fields.Selection(
        VISIT_OUTCOMES, string="Last visit outcome", readonly=True, copy=False
    )
    # Importer bookkeeping: which spreadsheet row this task comes from, so a
    # second import updates instead of duplicating.
    field_visit_import_key = fields.Char(
        copy=False, readonly=True, index="btree_not_null"
    )
    field_visit_import_observations = fields.Text(copy=False, readonly=True)

    _field_visit_import_key_unique = models.Constraint(
        "UNIQUE(project_id, field_visit_import_key)",
        "A business can only have one task per field-visit project.",
    )

    @api.depends("business_company_id")
    def _compute_business_partner_id(self):
        for task in self:
            if task.business_company_id:
                task.business_partner_id = task.business_company_id.partner_id

    @api.depends("business_company_id")
    def _compute_business_website_id(self):
        Website = self.env["website"].sudo()
        for task in self:
            company = task.business_company_id
            if not company:
                continue
            if task.business_website_id.company_id == company:
                continue
            task.business_website_id = Website.search(
                [("company_id", "=", company.id)], order="id", limit=1
            )

    @api.depends("business_company_id.name", "business_partner_id.name")
    def _compute_business_name(self):
        for task in self:
            task.business_name = (
                task.business_company_id.name or task.business_partner_id.name or False
            )

    @api.depends("business_website_id.domain")
    def _compute_business_microsite_url(self):
        for task in self:
            domain = (task.business_website_id.domain or "").strip()
            if domain and "://" not in domain:
                domain = f"https://{domain}"
            task.business_microsite_url = domain or False

    def action_open_business_microsite(self):
        self.ensure_one()
        if not self.business_microsite_url:
            return False
        return {
            "type": "ir.actions.act_url",
            "url": self.business_microsite_url,
            "target": "new",
        }

    def action_log_field_visit(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Log visit"),
            "res_model": "project.field.visit.log",
            "view_mode": "form",
            "target": "new",
            "context": {"default_task_id": self.id},
        }

    @api.model
    def _field_visit_action(self, domain, context):
        """Tasks of a business across every phase project."""
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Field visits"),
            "res_model": "project.task",
            "view_mode": "list,kanban,form",
            "domain": domain + [("project_id.is_field_visit_project", "=", True)],
            "context": context,
        }
