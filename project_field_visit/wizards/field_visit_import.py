# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import csv
import difflib
import io
import logging
import re
import unicodedata
from urllib.parse import urlsplit

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import openpyxl
except ImportError:  # pragma: no cover - the Doodba image ships it
    openpyxl = None
    _logger.warning("openpyxl is missing: field visit import accepts .csv only")

# Spreadsheet header (normalized) -> column key. Matched by prefix so
# "Comercio (razón social)" and trailing spaces or accents do not matter.
HEADERS = [
    ("total", "total"),
    ("anexo", "annex_number"),
    ("cantidad por seccion", "section_row"),
    ("comercio", "legal_name"),
    ("nombre comercial", "trade_name"),
    ("microsite", "microsite"),
    ("subdominio", "subdomain"),
    ("justificados en listado", "justified_list"),
    ("evidencias graficas", "graphic_evidence"),
    ("compromisos firmados", "commitment_signed"),
    ("estado participacion", "participation_status"),
    ("formacion", "training"),
    ("declaracion firmada", "declaration_signed"),
    ("observaciones", "observations"),
]

YES_NO_PENDING = {"si": "yes", "no": "no", "pendiente": "pending"}
PARTICIPATION = {
    "si": "yes",
    "pendiente": "pending",
    "no": "no",
    "nueva adhesion": "new",
    "nueva adhesion/pendiente": "new_pending",
    "nueva adhesion / pendiente": "new_pending",
    "posible adhesion": "prospect",
    "cerrado": "closed",
    "no quiere continuar": "withdrawn",
}
SELECTION_COLUMNS = {
    "justified_list": YES_NO_PENDING,
    "graphic_evidence": YES_NO_PENDING,
    "commitment_signed": YES_NO_PENDING,
    "training": YES_NO_PENDING,
    "declaration_signed": YES_NO_PENDING,
    "participation_status": PARTICIPATION,
}
LEGAL_SUFFIX = re.compile(
    r"(\s+(s\s?l\s?u|s\s?l\s?l|s\s?l|s\s?a|s\s?c\s?p|c\s?b|s\s?coop))+$"
)
FUZZY_CUTOFF = 0.92


def normalize(value):
    """Casefolded text without accents, extra spaces or trailing blanks."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.casefold().split())


def name_key(value):
    """Comparable business name: no punctuation, no legal form suffix."""
    text = re.sub(r"[^\w]+", " ", normalize(value)).strip()
    return LEGAL_SUFFIX.sub("", text).strip()


def subdomain_slug(value):
    """First label of a host, whether the cell holds a slug or a URL."""
    text = normalize(value).strip("/ ")
    if not text:
        return ""
    if "://" in text:
        text = urlsplit(text).hostname or ""
    return text.split("/")[0].split(".")[0]


def as_int(value):
    """Whole number of a cell, numeric or text (CSV); ``None`` otherwise."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return int(value)
    text = clean(value)
    if re.fullmatch(r"\d+(\.0+)?", text):
        return int(float(text))
    return None


def clean(value):
    if value is None:
        return ""
    return " ".join(str(value).split())


def stage_label(value):
    text = clean(value)
    return text[:1].upper() + text[1:].lower()


class ProjectFieldVisitImport(models.TransientModel):
    _name = "project.field.visit.import"
    _description = "Import field visits from a spreadsheet"

    project_id = fields.Many2one(
        "project.project",
        string="Phase project",
        domain="[('is_field_visit_project', '=', True)]",
    )
    new_project_name = fields.Char(
        string="New phase project",
        default=lambda self: self.env._("Door-to-door consulting - Phase I"),
    )
    file = fields.Binary(string="Spreadsheet", attachment=False)
    filename = fields.Char()
    dry_run = fields.Boolean(
        string="Dry run",
        default=True,
        help="Read the spreadsheet and report what would happen, without "
        "changing anything.",
    )
    update_stages = fields.Boolean(
        string="Move existing tasks to the spreadsheet section",
        help="By default a re-import leaves existing tasks in the stage the "
        "consultants moved them to.",
    )
    state = fields.Selection([("draft", "Draft"), ("done", "Done")], default="draft")
    summary = fields.Text(readonly=True)

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------
    def _read_rows(self):
        """All rows of the first sheet as lists of cell values."""
        self.ensure_one()
        if not self.file:
            raise UserError(self.env._("Upload the spreadsheet first."))
        content = base64.b64decode(self.file)
        name = (self.filename or "").lower()
        if name.endswith(".csv"):
            text = content.decode("utf-8-sig")
            try:
                dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            return [list(row) for row in csv.reader(io.StringIO(text), dialect)]
        if openpyxl is None:
            raise UserError(
                self.env._(
                    "Reading .xlsx files needs the openpyxl library, which is not "
                    "installed. Save the sheet as .csv and upload that instead."
                )
            )
        try:
            book = openpyxl.load_workbook(
                io.BytesIO(content), read_only=True, data_only=True
            )
        except Exception as error:
            raise UserError(
                self.env._("This file could not be read as an .xlsx spreadsheet.")
            ) from error
        sheet = book.worksheets[0]
        rows = [list(row) for row in sheet.iter_rows(values_only=True)]
        book.close()
        return rows

    @api.model
    def _parse_rows(self, rows):
        """Split the sheet into section labels and business rows.

        :return: (records, skipped) where each record is a dict with the
            column keys plus ``section`` (label of the section row above it).
        """
        header_index, columns = None, {}
        for index, row in enumerate(rows[:15]):
            found = {}
            for col, cell in enumerate(row):
                text = normalize(cell)
                for prefix, key in HEADERS:
                    if text.startswith(prefix) and key not in found:
                        found[key] = col
                        break
            if "subdomain" in found and (
                "legal_name" in found or "trade_name" in found
            ):
                header_index, columns = index, found
                break
        if header_index is None:
            raise UserError(
                self.env._(
                    "No header row found: the sheet needs at least the columns "
                    "'Comercio (razón social)' or 'Nombre comercial', and 'Subdominio'."
                )
            )

        def cell(row, key):
            col = columns.get(key)
            return row[col] if col is not None and col < len(row) else None

        records, skipped, section = [], 0, None
        for row in rows[header_index + 1 :]:
            legal, trade = clean(cell(row, "legal_name")), clean(
                cell(row, "trade_name")
            )
            first = cell(row, "total")
            if not legal and not trade:
                if clean(first) and as_int(first) is None:
                    section = stage_label(first)
                continue
            # A business row is numbered in the first column; anything else
            # with text in the name columns is a stray note.
            if "total" in columns and as_int(first) is None:
                skipped += 1
                continue
            if len(legal or trade) < 2:
                skipped += 1
                continue
            record = {key: cell(row, key) for key in columns}
            record.update(legal_name=legal, trade_name=trade, section=section)
            records.append(record)
        return records, skipped

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------
    @api.model
    def _matching_index(self):
        websites = self.env["website"].sudo().with_context(active_test=False).search([])
        by_slug = {}
        for website in websites:
            slug = subdomain_slug(website.domain)
            if slug and website.company_id:
                by_slug.setdefault(slug, website)
        companies = (
            self.env["res.company"].sudo().with_context(active_test=False).search([])
        )
        by_name = {}
        for company in companies:
            key = name_key(company.name)
            if key:
                by_name.setdefault(key, self.env["res.company"].sudo())
                by_name[key] |= company
        return by_slug, by_name

    @api.model
    def _match_business(self, record, index):
        """Find the platform company of a spreadsheet row.

        :return: (company, website, method) with method one of ``subdomain``,
            ``name``, ``fuzzy`` or ``None`` when nothing matches.
        """
        by_slug, by_name = index
        company = self.env["res.company"]
        slug = subdomain_slug(record.get("subdomain"))
        if slug and slug in by_slug:
            website = by_slug[slug]
            return website.company_id, website, "subdomain"
        keys = [
            k
            for k in (name_key(record["legal_name"]), name_key(record["trade_name"]))
            if k
        ]
        for key in keys:
            if len(by_name.get(key, company)) == 1:
                return by_name[key], None, "name"
        for key in keys:
            if len(key) < 4:
                continue
            close = difflib.get_close_matches(
                key, list(by_name), n=2, cutoff=FUZZY_CUTOFF
            )
            # Only an unambiguous near-match: two candidates means guessing.
            if len(close) == 1 and len(by_name[close[0]]) == 1:
                return by_name[close[0]], None, "fuzzy"
        return company, None, None

    # ------------------------------------------------------------------
    # Values
    # ------------------------------------------------------------------
    @api.model
    def _property_values(self, record, definition_names):
        """Checklist values of a row, only for properties the phase defines."""
        values, warnings = {}, []
        annex = as_int(record.get("annex_number"))
        if "annex_number" in definition_names and annex is not None:
            values["annex_number"] = annex
        if "microsite" in definition_names and "microsite" in record:
            values["microsite"] = normalize(record["microsite"]) == "x"
        for key, mapping in SELECTION_COLUMNS.items():
            raw = normalize(record.get(key))
            if key not in definition_names or not raw:
                continue
            if raw in mapping:
                values[key] = mapping[raw]
            else:
                warnings.append((key, clean(record.get(key))))
        return values, warnings

    def _stage_map(self, project, records, dry_run):
        """Stage of each section label, creating the missing ones."""
        existing = {normalize(stage.name): stage for stage in project.type_ids}
        stages, created = {}, []
        sequence = max(project.type_ids.mapped("sequence") or [0])
        for label in dict.fromkeys(r["section"] for r in records if r["section"]):
            stage = existing.get(normalize(label))
            if not stage:
                created.append(label)
                if dry_run:
                    continue
                sequence += 1
                stage = self.env["project.task.type"].create(
                    {
                        "name": label,
                        "sequence": sequence,
                        "project_ids": [(4, project.id)],
                    }
                )
            stages[label] = stage
        return stages, created

    @api.model
    def _observations_body(self, text):
        return Markup(
            "<p><strong>%s</strong></p><p style='white-space: pre-wrap'>%s</p>"
        ) % (
            self.env._("Observations imported from the spreadsheet"),
            escape(text),
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_create_phase_project(self):
        self.ensure_one()
        name = clean(self.new_project_name)
        if not name:
            raise UserError(self.env._("Give the new phase project a name."))
        project = self.env["project.project"].create(
            {"name": name, "is_field_visit_project": True}
        )
        project._field_visit_ensure_properties()
        self.project_id = project
        return self._reopen()

    def action_import(self):
        self.ensure_one()
        if not self.project_id:
            raise UserError(self.env._("Choose or create the phase project first."))
        records, skipped = self._parse_rows(self._read_rows())
        self.summary = self._run_import(records, skipped, self.dry_run)
        self.state = "done"
        return self._reopen()

    def action_back(self):
        self.ensure_one()
        self.state = "draft"
        return self._reopen()

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "name": self.env._("Import field visits"),
        }

    def _run_import(self, records, skipped, dry_run):
        """Create or update one task per business; return a summary text."""
        self.ensure_one()
        project = self.project_id
        Task = self.env["project.task"].with_context(
            active_test=False, mail_create_nolog=True
        )
        definition_missing = not project.task_properties_definition
        if definition_missing and not dry_run:
            project._field_visit_ensure_properties()
        definition = (
            project.task_properties_definition
            or project._field_visit_phase_one_properties()
        )
        definition_names = {prop["name"] for prop in definition}
        stages, created_stages = self._stage_map(project, records, dry_run)
        index = self._matching_index()
        existing = self._existing_tasks(Task, project)
        counts = dict.fromkeys(
            ("created", "updated", "subdomain", "name", "fuzzy", "prospect"), 0
        )
        unmatched, warnings = [], []
        seen = set()
        for record in records:
            company, website, method = self._match_business(record, index)
            display = record["trade_name"] or record["legal_name"]
            name_ref = "name:" + name_key(display)
            key = f"company:{company.id}" if company else name_ref
            if key in seen:
                warnings.append(self.env._("Duplicate row skipped: %s", display))
                continue
            seen.add(key)
            counts[method or "prospect"] += 1
            if not company:
                unmatched.append(display)
            # A prospect that joined the platform since the last import
            # keeps its task: the name key is upgraded to the company key.
            task = existing.get(key) or (company and existing.get(name_ref))
            props, row_warnings = self._property_values(record, definition_names)
            warnings += [
                self.env._(
                    "%(business)s: unknown value %(value)r in %(column)s",
                    business=display,
                    value=value,
                    column=column,
                )
                for column, value in row_warnings
            ]
            counts["updated" if task else "created"] += 1
            if dry_run:
                continue
            existing[key] = self._save_task(
                Task, task, record, key, company, website, props, stages
            )
        return self._summary_text(
            dry_run,
            len(records),
            skipped,
            counts,
            created_stages,
            definition_missing,
            unmatched,
            warnings,
        )

    @api.model
    def _existing_tasks(self, Task, project):
        """Tasks of the project by import key."""
        existing = {}
        for task in Task.search(
            [
                ("project_id", "=", project.id),
                "|",
                ("field_visit_import_key", "!=", False),
                ("business_company_id", "!=", False),
            ]
        ):
            # Tasks created by hand for a platform business count too.
            if task.business_company_id:
                existing.setdefault(f"company:{task.business_company_id.id}", task)
            if task.field_visit_import_key:
                existing[task.field_visit_import_key] = task
        return existing

    def _save_task(self, Task, task, record, key, company, website, props, stages):
        """Write one spreadsheet row on its task (created when missing)."""
        display = record["trade_name"] or record["legal_name"]
        vals = {"field_visit_import_key": key}
        if props:
            vals["task_properties"] = props
        stage = stages.get(record["section"])
        if company:
            vals["business_company_id"] = company.id
            if website:
                vals["business_website_id"] = website.id
        if task:
            if stage and self.update_stages:
                vals["stage_id"] = stage.id
            task.write(vals)
        else:
            vals.update(
                name=record["trade_name"] or company.name or display,
                project_id=self.project_id.id,
            )
            if stage:
                vals["stage_id"] = stage.id
            if not company:
                vals["business_partner_id"] = self._prospect_partner(display).id
            task = Task.create(vals)
        observations = str(record.get("observations") or "").strip()
        if observations and observations != (
            task.field_visit_import_observations or ""
        ):
            task.message_post(
                body=self._observations_body(observations),
                subtype_xmlid="mail.mt_note",
            )
            task.field_visit_import_observations = observations
        return task

    @api.model
    def _prospect_partner(self, name):
        return self.env["res.partner"].create({"name": name, "is_company": True})

    def _summary_text(
        self,
        dry_run,
        total,
        skipped,
        counts,
        created_stages,
        definition_missing,
        unmatched,
        warnings,
    ):
        _ = self.env._
        lines = [
            _("DRY RUN: nothing was changed.") if dry_run else _("Import finished."),
            _("Business rows read: %s", total),
            _("Rows skipped (no number or no name): %s", skipped),
            _("Tasks created: %s", counts["created"]),
            _("Tasks updated: %s", counts["updated"]),
            _("Matched by subdomain: %s", counts["subdomain"]),
            _("Matched by exact name: %s", counts["name"]),
            _("Matched by similar name: %s", counts["fuzzy"]),
            _("Not on the platform (prospect contacts): %s", counts["prospect"]),
        ]
        if created_stages:
            lines.append(_("New stages: %s", ", ".join(created_stages)))
        if definition_missing:
            lines.append(
                _(
                    "The project has no checklist fields: the phase I fields would be added."
                )
                if dry_run
                else _("The phase I checklist fields were added to the project.")
            )
        if unmatched:
            lines += ["", _("Businesses without a platform company:")]
            lines += [f"- {name}" for name in unmatched]
        if warnings:
            lines += ["", _("Warnings:")] + [f"- {w}" for w in warnings]
        return "\n".join(lines)
