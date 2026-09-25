# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

CONSULTANT_GROUP = "project_field_visit.group_field_visit_consultant"
MANAGER_GROUP = "project_field_visit.group_field_visit_manager"

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

    # Stored: the global record rule filters on it without a subquery on
    # project.project (which would apply the project rules and hide tasks a
    # user follows in a project they cannot read).
    is_field_visit_project = fields.Boolean(
        related="project_id.is_field_visit_project", store=True, index=True
    )
    # The VISITED business. Not ``company_id``: that one is the company that
    # owns the task (the programme), and the visited business is usually
    # outside the consultant's allowed companies. Hence no ``check_company``
    # and the stored ``business_name`` / ``business_microsite_url`` below:
    # a consultant reads the task without ever reading the business records.
    business_company_id = fields.Many2one(
        "res.company",
        groups=CONSULTANT_GROUP,
        string="Visited business",
        index="btree_not_null",
        ondelete="set null",
        tracking=True,
        help="Business of the platform this task documents.",
    )
    business_partner_id = fields.Many2one(
        "res.partner",
        groups=CONSULTANT_GROUP,
        string="Business contact",
        compute="_compute_business_partner_id",
        store=True,
        readonly=False,
        index="btree_not_null",
        ondelete="set null",
        tracking=True,
        domain="[('is_field_visit_prospect', '=', True)]",
        help="Contact of the visited business. For a business that is not on "
        "the platform yet (a prospect) this is the only link.",
    )
    business_website_id = fields.Many2one(
        "website",
        groups=CONSULTANT_GROUP,
        string="Microsite",
        compute="_compute_business_website_id",
        store=True,
        readonly=False,
        ondelete="set null",
    )
    business_name = fields.Char(
        groups=CONSULTANT_GROUP,
        compute="_compute_business_name",
        store=True,
        string="Business",
    )
    business_microsite_url = fields.Char(
        groups=CONSULTANT_GROUP,
        compute="_compute_business_microsite_url",
        store=True,
        string="Microsite URL",
    )
    field_visit_last_date = fields.Datetime(
        groups=CONSULTANT_GROUP, string="Last visit", readonly=True, copy=False
    )
    field_visit_last_outcome = fields.Selection(
        VISIT_OUTCOMES,
        string="Last visit outcome",
        readonly=True,
        copy=False,
        groups=CONSULTANT_GROUP,
    )
    # Importer bookkeeping: which spreadsheet row this task comes from, so a
    # second import updates instead of duplicating.
    field_visit_import_key = fields.Char(
        groups=CONSULTANT_GROUP, copy=False, readonly=True, index="btree_not_null"
    )
    field_visit_import_observations = fields.Text(
        groups=CONSULTANT_GROUP, copy=False, readonly=True
    )

    _field_visit_import_key_unique = models.Constraint(
        "UNIQUE(project_id, field_visit_import_key)",
        "A business can only have one task per field-visit project.",
    )
    # One task per business and phase, whoever creates it (importer, form,
    # duplicate button): a platform business by its company, a prospect by
    # its contact.
    _field_visit_business_company_unique = models.UniqueIndex(
        "(project_id, business_company_id) WHERE business_company_id IS NOT NULL",
        "This business already has a task in this field-visit project.",
    )
    _field_visit_business_partner_unique = models.UniqueIndex(
        "(project_id, business_partner_id) "
        "WHERE business_company_id IS NULL AND business_partner_id IS NOT NULL",
        "This prospect already has a task in this field-visit project.",
    )

    @api.constrains("business_company_id", "business_partner_id")
    def _check_business_partner(self):
        """The contact is the business's own, or a field-visit prospect.

        Any other contact would let a task point at (and display the name
        of) an arbitrary person of the database.
        """
        for task in self.sudo():
            partner, company = task.business_partner_id, task.business_company_id
            if not partner:
                continue
            if company and partner != company.partner_id:
                raise ValidationError(
                    self.env._(
                        "The business contact must be the contact of the "
                        "visited business."
                    )
                )
            if not company and not partner.is_field_visit_prospect:
                raise ValidationError(
                    self.env._(
                        "Without a platform business, the contact must be a "
                        "field-visit prospect."
                    )
                )

    @api.model
    def _check_field_visit_access(self, group=CONSULTANT_GROUP):
        if not (self.env.su or self.env.user.has_group(group)):
            raise AccessError(self.env._("Only field visit consultants can do this."))

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
        self._check_field_visit_access()
        if not self.business_microsite_url:
            return False
        return {
            "type": "ir.actions.act_url",
            "url": self.business_microsite_url,
            "target": "new",
        }

    def action_log_field_visit(self):
        self.ensure_one()
        self._check_field_visit_access()
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
        self._check_field_visit_access()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Field visits"),
            "res_model": "project.task",
            "view_mode": "list,kanban,form",
            "domain": domain + [("is_field_visit_project", "=", True)],
            "context": context,
        }
