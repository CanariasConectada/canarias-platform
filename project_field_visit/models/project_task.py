# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from urllib.parse import quote_plus

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

CONSULTANT_GROUP = "project_field_visit.group_field_visit_consultant"
MANAGER_GROUP = "project_field_visit.group_field_visit_manager"
VISIT_ACTIVITY_TYPE = "project_field_visit.mail_activity_type_field_visit"
MAPS_SEARCH_URL = "https://www.google.com/maps/search/?api=1&query="

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
    # Where and whom to visit. Every phase needs them, so they are fields,
    # not phase properties; the importer fills them from the tracking list.
    field_visit_address = fields.Char(
        string="Business address", groups=CONSULTANT_GROUP
    )
    field_visit_map_url = fields.Char(
        string="Map",
        compute="_compute_field_visit_map_url",
        groups=CONSULTANT_GROUP,
    )
    field_visit_zone = fields.Char(
        string="Zone", index="btree_not_null", groups=CONSULTANT_GROUP
    )
    field_visit_phone = fields.Char(string="Business phone", groups=CONSULTANT_GROUP)
    field_visit_email = fields.Char(string="Business email", groups=CONSULTANT_GROUP)
    # Filled by ``_field_visit_refresh_microsite_status`` (daily cron, the
    # managers' action and a change of business), not computed: checking a
    # microsite reads its homepage arch and attachments.
    field_visit_microsite_missing = fields.Text(
        string="Missing microsite information",
        groups=CONSULTANT_GROUP,
        readonly=True,
        copy=False,
    )
    field_visit_microsite_complete = fields.Boolean(
        string="Information complete",
        groups=CONSULTANT_GROUP,
        readonly=True,
        copy=False,
    )
    field_visit_contact_name = fields.Char(
        string="Contact person", groups=CONSULTANT_GROUP
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

    @api.depends("field_visit_address")
    def _compute_field_visit_map_url(self):
        for task in self:
            address = " ".join((task.field_visit_address or "").split())
            task.field_visit_map_url = (
                MAPS_SEARCH_URL + quote_plus(address) if address else False
            )

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        tasks.filtered(
            lambda t: t.is_field_visit_project and t.date_deadline and t.user_ids
        )._field_visit_sync_reminders()
        tasks.filtered("is_field_visit_project")._field_visit_refresh_microsite_status()
        return tasks

    def write(self, vals):
        res = super().write(vals)
        if {
            "date_deadline",
            "user_ids",
            "project_id",
            "stage_id",
            "state",
        } & vals.keys():
            self._field_visit_sync_reminders()
        if "business_company_id" in vals:
            self._field_visit_refresh_microsite_status()
        return res

    def _field_visit_refresh_microsite_status(self):
        """Store what the microsite of each task's business still lacks.

        One check per business (``_get_microsite_missing_items`` is batched).
        A task without a business (a prospect) has no status; a task is only
        written when its status changed.
        """
        tasks = self.sudo()
        companies = tasks.business_company_id
        missing = companies._get_microsite_missing_items() if companies else {}
        for task in tasks:
            company = task.business_company_id
            items = missing.get(company.id, [])
            values = {
                "field_visit_microsite_missing": "\n".join(items) or False,
                "field_visit_microsite_complete": bool(company) and not items,
            }
            if any(task[name] != value for name, value in values.items()):
                task.write(values)

    @api.model
    def _cron_field_visit_refresh_microsite_status(self):
        self.sudo().search(
            [
                ("is_field_visit_project", "=", True),
                ("business_company_id", "!=", False),
            ]
        )._field_visit_refresh_microsite_status()

    def action_field_visit_refresh_microsite_status(self):
        self._check_field_visit_access(MANAGER_GROUP)
        self._field_visit_refresh_microsite_status()

    def _field_visit_sync_reminders(self):
        """One *Field visit* activity per assigned consultant, on the visit day.

        Follows the planned date (``date_deadline``) and the assignees: a
        moved date moves the reminder, a removed assignee or a closed task
        loses it. Past dates get none. Quiet: no e-mail per reminder, they
        show in the activity menu.
        """
        tasks = self.filtered("is_field_visit_project")
        activity_type = tasks and self.env.ref(VISIT_ACTIVITY_TYPE, False)
        if not activity_type:
            return
        today = fields.Date.context_today(self)
        for task in tasks:
            day = task.date_deadline and fields.Date.context_today(
                task, timestamp=task.date_deadline
            )
            wanted = self.env["res.users"]
            if day and day >= today and not task.is_closed:
                wanted = task.user_ids.filtered(
                    lambda u: not u.share and u.has_group(CONSULTANT_GROUP)
                )
            current = task.sudo().activity_ids.filtered(
                lambda a, t=activity_type: a.activity_type_id == t
            )
            kept = current.browse()
            for activity in current:
                if activity.user_id not in wanted:
                    activity.unlink()
                    continue
                kept |= activity
                if activity.date_deadline != day:
                    activity.date_deadline = day
            for user in wanted - kept.user_id:
                task.with_context(mail_activity_quick_update=True).activity_schedule(
                    activity_type_id=activity_type.id,
                    date_deadline=day,
                    user_id=user.id,
                    summary=self.env._(
                        "Visit %s", task.sudo().business_name or task.name
                    ),
                )

    def _field_visit_done_reminders(self, user):
        """The visit happened: drop ``user``'s pending reminder."""
        activity_type = self.env.ref(VISIT_ACTIVITY_TYPE, False)
        if not activity_type:
            return
        self.sudo().activity_ids.filtered(
            lambda a: a.activity_type_id == activity_type and a.user_id == user
        ).unlink()

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
