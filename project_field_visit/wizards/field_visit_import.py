# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import csv
import datetime
import difflib
import io
import itertools
import logging
import re
from collections import defaultdict
from urllib.parse import urlsplit

from markupsafe import Markup, escape

from odoo import Command, api, fields, models
from odoo.exceptions import UserError

from ..models.project_task import CONSULTANT_GROUP, MANAGER_GROUP
from . import field_visit_tracking as tracking
from .sheet_utils import as_int, clean, normalize

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
# Below FUZZY_CUTOFF but above this, a prospect "looks like" a known one: the
# row is not linked nor duplicated, it goes to the review list.
REVIEW_CUTOFF = 0.8
# Hard limits, checked before the content is materialized.
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ROWS = 5000
MAX_COLUMNS = 60
MAX_SHEETS = 30


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


def names_agree(keys, company_key):
    """Whether a row's names designate the company.

    Equal keys, one name's words all contained in the other's ("zzfv bakery"
    and "panaderia zzfv bakery"), or a similar spelling.
    """
    if not company_key:
        return False
    company_words = set(company_key.split())
    for key in keys:
        if not key:
            continue
        if key == company_key:
            return True
        words = set(key.split())
        shorter = min((words, company_words), key=len)
        if len("".join(shorter)) >= 6 and (
            words <= company_words or company_words <= words
        ):
            return True
        if difflib.SequenceMatcher(None, key, company_key).ratio() >= FUZZY_CUTOFF:
            return True
    return False


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
    overwrite_values = fields.Boolean(
        string="Overwrite values from the spreadsheet",
        help="By default a re-import only fills what is empty on the tasks, "
        "so what the consultants typed in Odoo wins. Tick it when the sheet "
        "must win (checklist values, contact details, planned date).",
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
    def _file_content(self):
        self.ensure_one()
        if not self.file:
            raise UserError(self.env._("Upload the spreadsheet first."))
        # Base64 is 4/3 of the payload: refuse before decoding a huge upload.
        if len(self.file) * 3 // 4 > MAX_FILE_BYTES:
            raise UserError(self._too_big_message())
        content = base64.b64decode(self.file)
        if len(content) > MAX_FILE_BYTES:
            raise UserError(self._too_big_message())
        return content

    def _too_big_message(self):
        return self.env._(
            "The file is larger than %(size)s MB.", size=MAX_FILE_BYTES // 1024 // 1024
        )

    def _too_many_message(self):
        return self.env._(
            "The sheet has more than %(rows)s rows or %(columns)s columns.",
            rows=MAX_ROWS,
            columns=MAX_COLUMNS,
        )

    def _iter_sheets(self):
        """``(title, rows)`` of every sheet; rows are streamed lists of cells.

        A .csv file is one sheet. The limits apply to each sheet, checked
        before its content is read.
        """
        content = self._file_content()
        if (self.filename or "").lower().endswith(".csv"):
            yield clean(self.filename), self._limited(self._iter_csv(content))
            return
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
        try:
            if len(book.worksheets) > MAX_SHEETS:
                raise UserError(self._too_many_message())
            for sheet in book.worksheets:
                yield sheet.title, self._limited(self._iter_xlsx_sheet(sheet))
        finally:
            book.close()

    def _limited(self, rows):
        for count, row in enumerate(rows, start=1):
            if count > MAX_ROWS or len(row) > MAX_COLUMNS:
                raise UserError(self._too_many_message())
            yield row

    @api.model
    def _iter_csv(self, content):
        text = content.decode("utf-8-sig")
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        for row in csv.reader(io.StringIO(text), dialect):
            yield row

    def _iter_xlsx_sheet(self, sheet):
        # The declared dimension is cheap to check; the streamed count in
        # _limited catches a file that lies about it.
        if (sheet.max_row or 0) > MAX_ROWS or (sheet.max_column or 0) > MAX_COLUMNS:
            raise UserError(self._too_many_message())
        for row in sheet.iter_rows(values_only=True, max_col=MAX_COLUMNS + 1):
            # Trailing empty cells are padding, not columns.
            values = list(row)
            while values and values[-1] is None:
                values.pop()
            yield values

    def _read_sheets(self):
        """Business rows of the file, in one of the two known formats.

        The *checklist* (phase I evidence list: one sheet, numbered rows,
        section rows, a *Subdominio* column) is recognised on the first
        sheet. Anything else is read as the consultants' *tracking list*:
        every sheet with a business-name header is read and merged.

        :return: (format, records, skipped, info) where ``info`` holds the
            sheet notes, the columns ignored for privacy and the sizes of
            the sheets read (tracking list only).
        """
        _ = self.env._
        info = {"notes": [], "ignored": [], "sheets": []}
        sheets, first = [], True
        for title, rows in self._iter_sheets():
            if tracking.is_secret_sheet(title):
                # Never read: the client keeps credentials in the workbook.
                info["notes"].append(
                    _("Sheet '%s' skipped: it holds credentials.", title)
                )
                continue
            head = list(itertools.islice(rows, tracking.HEADER_SCAN))
            if first:
                first = False
                if not tracking.secret_headers(head[0] if head else []) and (
                    self._checklist_columns(head) is not None
                ):
                    checklist, skipped = self._parse_rows(itertools.chain(head, rows))
                    return "checklist", checklist, skipped, info
            layout, start, secret = None, 0, []
            for start, row in enumerate(head, start=1):
                # Default-deny: a credential-looking cell above or in the
                # header row makes the whole sheet unreadable.
                secret += tracking.secret_headers(row)
                layout = tracking.tracking_layout(row)
                if layout or secret:
                    break
            if secret or (layout and layout["secret"]):
                info["notes"].append(
                    _("Sheet '%s' skipped: it holds credentials.", title)
                )
                columns = secret or layout["ignored"]
                info["ignored"] += [f"{title}: {column}" for column in columns]
                continue
            if not layout:
                info["notes"].append(
                    _(
                        "Sheet '%s' skipped: no header with a business name column.",
                        title,
                    )
                )
                continue
            info["ignored"] += [f"{title}: {column}" for column in layout["ignored"]]
            sheet_records, sheet_skipped = tracking.parse_tracking_rows(
                itertools.chain(head[start:], rows), layout, title
            )
            sheets.append((title, layout, sheet_records, sheet_skipped))
        if not sheets:
            raise UserError(
                _(
                    "No header row found. A phase checklist needs the columns "
                    "'Comercio (razón social)' or 'Nombre comercial', and "
                    "'Subdominio'; a tracking list needs a business name column "
                    "('Nombre', 'Nombre comercial'...) and contact or follow-up "
                    "columns ('Zona', 'TLF', 'Dirección', 'Correo'...)."
                )
            )
        known = self._known_business_keys(
            [
                r
                for _t, layout, recs, _s in sheets
                if not layout["bare_name"]
                for r in recs
            ]
        )
        records, skipped = [], 0
        for title, layout, sheet_records, sheet_skipped in sheets:
            if layout["bare_name"] and not self._names_look_like_businesses(
                sheet_records, known
            ):
                info["notes"].append(
                    _(
                        "Sheet '%s' skipped: no business column (its 'Nombre' "
                        "does not name known businesses; rename it 'Nombre "
                        "comercial' if it does).",
                        title,
                    )
                )
                continue
            records += sheet_records
            skipped += sheet_skipped
            info["sheets"].append((title, len(sheet_records)))
            info["notes"].append(
                _(
                    "Sheet '%(sheet)s': %(rows)s business rows.",
                    sheet=title,
                    rows=len(sheet_records),
                )
            )
        if not info["sheets"]:
            raise UserError(
                _("No sheet of the file has a column with the business names.")
            )
        return "tracking", records, skipped, info

    def _known_business_keys(self, definite_records):
        """Name keys of the businesses the file can be checked against.

        Platform companies, the tasks and prospects of the phase, and the
        rows of the sheets whose business column is unambiguous.
        """
        _by_slug, by_name, archived = self._matching_index(self.project_id)
        keys = set(by_name) | archived
        Task = self.env["project.task"].with_context(active_test=False)
        for task in Task.search([("project_id", "=", self.project_id.id)]):
            keys |= {name_key(task.name), name_key(task.sudo().business_name)}
        keys |= {name_key(r["trade_name"]) for r in definite_records}
        keys.discard("")
        return keys

    @api.model
    def _names_look_like_businesses(self, records, known, sample=200):
        """Whether a bare "Nombre" column names businesses, not people.

        At least half of its (distinct) values must be known business
        names, exactly or nearly.
        """
        names = list(dict.fromkeys(name_key(r["trade_name"]) for r in records))
        names = [n for n in names if n][:sample]
        if not names:
            return False
        known_list = list(known)
        hits = sum(
            1
            for name in names
            if name in known
            or (
                len(name) >= 4
                and difflib.get_close_matches(
                    name, known_list, n=1, cutoff=FUZZY_CUTOFF
                )
            )
        )
        return hits * 2 >= len(names)

    @api.model
    def _checklist_columns(self, rows):
        """Columns of the checklist header among ``rows``, or ``None``."""
        for row in rows:
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
                return found
        return None

    @api.model
    def _parse_rows(self, rows):
        """Split the sheet into section labels and business rows.

        :param rows: iterable of rows (lists of cell values)
        :return: (records, skipped) where each record is a dict with the
            column keys plus ``section`` (label of the section row above it).
        """
        rows = iter(rows)
        columns = None
        for _index, row in zip(range(tracking.HEADER_SCAN), rows, strict=False):
            columns = self._checklist_columns([row])
            if columns is not None:
                break
        if columns is None:
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
        for row in rows:
            legal = clean(cell(row, "legal_name"))
            trade = clean(cell(row, "trade_name"))
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
    def _excluded_companies(self, project):
        """Companies that are never a visited business.

        The platform company, the zone companies (when the zone module is
        installed) and the company that owns the phase project.
        """
        Company = self.env["res.company"].sudo()
        excluded = self.env.ref("base.main_company").sudo() | project.sudo().company_id
        if "zone_company_key" in Company._fields:
            excluded |= Company.with_context(active_test=False).search(
                [("zone_company_key", "!=", False)]
            )
        return excluded

    @api.model
    def _matching_index(self, project):
        """Candidate businesses by microsite slug and by name key.

        Runs as superuser so that the manager sees every business of the
        platform, which is why only field visit managers get here.
        """
        self.env["project.task"]._check_field_visit_access(MANAGER_GROUP)
        excluded = self._excluded_companies(project)
        companies = (
            self.env["res.company"].sudo().search([("id", "not in", excluded.ids)])
        )
        by_slug = defaultdict(lambda: self.env["website"].sudo())
        for website in (
            self.env["website"].sudo().search([("company_id", "in", companies.ids)])
        ):
            slug = subdomain_slug(website.domain)
            if slug:
                by_slug[slug] |= website
        by_name = defaultdict(lambda: self.env["res.company"].sudo())
        for company in companies:
            key = name_key(company.name)
            if key:
                by_name[key] |= company
        # Never linked, but a row naming one is not a new prospect either.
        archived = {
            name_key(company.name)
            for company in self.env["res.company"]
            .sudo()
            .with_context(active_test=False)
            .search([("active", "=", False), ("id", "not in", excluded.ids)])
        }
        return dict(by_slug), dict(by_name), archived

    @api.model
    def _match_business(self, record, index):
        """Find the platform company of a spreadsheet row.

        :return: (company, website, method, review) where method is
            ``subdomain``, ``name``, ``fuzzy`` or ``None``, and ``review`` is
            the reason a manager must look at the row (nothing is linked).
        """
        by_slug, by_name, archived = index
        none = self.env["res.company"]
        keys = [
            k
            for k in (name_key(record["legal_name"]), name_key(record["trade_name"]))
            if k
        ]
        slug = subdomain_slug(record.get("subdomain"))
        if slug and slug in by_slug:
            websites = by_slug[slug]
            if len(websites) > 1:
                return (
                    none,
                    None,
                    None,
                    self.env._("subdomain '%s' belongs to several websites", slug),
                )
            company = websites.company_id
            if not names_agree(keys, name_key(company.name)):
                return (
                    none,
                    None,
                    None,
                    self.env._(
                        "subdomain '%(slug)s' belongs to '%(company)s', whose name "
                        "does not match",
                        slug=slug,
                        company=company.name,
                    ),
                )
            return company, websites, "subdomain", None
        for key in keys:
            if len(by_name.get(key, none)) == 1:
                return by_name[key], None, "name", None
        for key in keys:
            if len(key) < 4:
                continue
            close = difflib.get_close_matches(
                key, list(by_name), n=2, cutoff=FUZZY_CUTOFF
            )
            # Only an unambiguous near-match: two candidates means guessing.
            if len(close) == 1 and len(by_name[close[0]]) == 1:
                return by_name[close[0]], None, "fuzzy", None
        if archived.intersection(keys):
            return none, None, None, self.env._("matches an archived company")
        return none, None, None, None

    @api.model
    def _match_prospect(self, record, prospects):
        """Known prospect partner of a row without a platform company.

        :param prospects: prospect partners already linked to the project
        :return: (partner or empty, review reason or None)
        """
        none = self.env["res.partner"]
        key = name_key(record["trade_name"] or record["legal_name"])
        annex = as_int(record.get("annex_number"))

        def compatible(partner):
            # Two same-named businesses with different annex numbers are
            # two businesses.
            known = partner.field_visit_annex_number
            return not (annex and known and annex != known)

        same = prospects.filtered(
            lambda p: p.field_visit_prospect_key == key and compatible(p)
        )
        exact = same.filtered(lambda p: annex and p.field_visit_annex_number == annex)
        if len(exact) == 1:
            return exact, None
        if len(same) == 1:
            return same, None
        if len(same) > 1:
            return none, self.env._("several known prospects are called like this")
        # Renamed in the sheet since the last import?
        scored = sorted(
            (
                (
                    difflib.SequenceMatcher(
                        None, key, p.field_visit_prospect_key or ""
                    ).ratio(),
                    p,
                )
                for p in prospects
                if compatible(p)
            ),
            key=lambda pair: pair[0],
            reverse=True,
        )
        best = [p for ratio, p in scored if ratio >= FUZZY_CUTOFF]
        if len(best) == 1:
            return best[0], None
        if best or any(ratio >= REVIEW_CUTOFF for ratio, _p in scored):
            return none, self.env._(
                "looks like a known prospect, but not surely the same"
            )
        return none, None

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
        self.env["project.task"]._check_field_visit_access(MANAGER_GROUP)
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
        self.env["project.task"]._check_field_visit_access(MANAGER_GROUP)
        if not self.project_id:
            raise UserError(self.env._("Choose or create the phase project first."))
        file_format, records, skipped, info = self._read_sheets()
        if file_format == "checklist":
            self.summary = self._run_import(records, skipped, self.dry_run)
        else:
            self.summary = self._run_tracking_import(
                records, skipped, info, self.dry_run
            )
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

    @api.model
    def _existing_tasks(self, Task, project):
        """Tasks of the project by business: ``company:<id>`` / ``partner:<id>``."""
        existing = {}
        for task in Task.search(
            [
                ("project_id", "=", project.id),
                "|",
                ("business_company_id", "!=", False),
                ("business_partner_id", "!=", False),
            ]
        ):
            if task.business_company_id:
                existing[f"company:{task.business_company_id.id}"] = task
            else:
                existing[f"partner:{task.business_partner_id.id}"] = task
        return existing

    @api.model
    def _known_prospects(self, existing):
        tasks = [task for key, task in existing.items() if key.startswith("partner:")]
        partners = self.env["res.partner"].union(
            *(task.business_partner_id for task in tasks)
        )
        return partners.filtered("is_field_visit_prospect")

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
        index = self._matching_index(project)
        existing = self._existing_tasks(Task, project)
        counts = dict.fromkeys(
            ("created", "updated", "subdomain", "name", "fuzzy", "prospect"), 0
        )
        unmatched, review, warnings = [], [], []
        seen = set()
        for record in records:
            display = record["trade_name"] or record["legal_name"]
            company, website, method, reason = self._match_business(record, index)
            prospect = self.env["res.partner"]
            if not company and not reason:
                prospects = self._known_prospects(existing)
                prospect, reason = self._match_prospect(record, prospects)
            if reason:
                review.append(f"{display}: {reason}")
                continue
            if company:
                key = f"company:{company.id}"
            elif prospect:
                key = f"partner:{prospect.id}"
            else:
                key = "new:%s:%s" % (
                    name_key(display),
                    as_int(record.get("annex_number")) or "",
                )
            if key in seen:
                warnings.append(self.env._("Duplicate row skipped: %s", display))
                continue
            seen.add(key)
            counts[method or "prospect"] += 1
            if not company:
                unmatched.append(display)
            task = existing.get(key)
            if company and not task:
                # A prospect that joined the platform since the last import
                # keeps its task.
                prospects = self._known_prospects(existing)
                former, _reason = self._match_prospect(record, prospects)
                task = former and existing.pop(f"partner:{former.id}")
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
            task = self._save_task(Task, task, record, company, website, props, stages)
            existing[
                (
                    f"company:{company.id}"
                    if company
                    else f"partner:{task.business_partner_id.id}"
                )
            ] = task
        return self._summary_text(
            dry_run,
            len(records),
            skipped,
            counts,
            created_stages,
            definition_missing,
            unmatched,
            review,
            warnings,
        )

    def _save_task(self, Task, task, record, company, website, props, stages):
        """Write one spreadsheet row on its task (created when missing)."""
        display = record["trade_name"] or record["legal_name"]
        vals = {}
        if props:
            vals["task_properties"] = self._merged_properties(
                task, props, self.overwrite_values
            )
        stage = stages.get(record["section"])
        if company:
            vals["business_company_id"] = company.id
            vals["field_visit_import_key"] = f"company:{company.id}"
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
                # Not the importing manager: consultants are assigned later.
                user_ids=[Command.set([])],
            )
            if stage:
                vals["stage_id"] = stage.id
            if not company:
                partner = self._prospect_partner(record)
                vals["business_partner_id"] = partner.id
                vals["field_visit_import_key"] = f"partner:{partner.id}"
            task = Task.create(vals)
        self._post_observations(task, record.get("observations"))
        return task

    @api.model
    def _post_observations(self, task, observations):
        """Post the sheet's notes once; a changed note is posted again."""
        observations = str(observations or "").strip()
        if observations and observations != (
            task.field_visit_import_observations or ""
        ):
            task.message_post(
                body=self._observations_body(observations),
                subtype_xmlid="mail.mt_note",
            )
            task.field_visit_import_observations = observations

    @api.model
    def _merged_properties(self, task, values, overwrite=False):
        """Property values of ``task`` completed with ``values``.

        Writing a dict replaces every value of the task, so the current
        values are carried over. Like the task fields, a sheet value only
        fills an unset property unless ``overwrite``: what a consultant
        typed in Odoo survives a re-import.
        """
        if not task:
            return dict(values)
        current = {}
        for prop in task.read(["task_properties"])[0]["task_properties"]:
            value = prop.get("value")
            if prop.get("type") == "many2one" and isinstance(value, list | tuple):
                value = value[0] if value else False
            elif prop.get("type") in ("many2many", "tags") and value:
                value = [v[0] if isinstance(v, list | tuple) else v for v in value]
            current[prop["name"]] = value
        for name, value in values.items():
            if overwrite or self._is_unset(current.get(name)):
                current[name] = value
        return current

    @staticmethod
    def _is_unset(value):
        return value is None or value is False or value == "" or value == []

    @api.model
    def _prospect_partner(self, record):
        display = record["trade_name"] or record["legal_name"]
        return self.env["res.partner"].create(
            {
                "name": display,
                "is_company": True,
                "is_field_visit_prospect": True,
                "field_visit_prospect_key": name_key(display),
                "field_visit_annex_number": as_int(record.get("annex_number")),
            }
        )

    def _summary_text(
        self,
        dry_run,
        total,
        skipped,
        counts,
        created_stages,
        definition_missing,
        unmatched,
        review,
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
            _("To review (not imported): %s", len(review)),
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
        if review:
            lines += [
                "",
                _("To review (fix the sheet or the company, then re-import):"),
            ]
            lines += [f"- {line}" for line in review]
        if unmatched:
            lines += ["", _("Businesses without a platform company:")]
            lines += [f"- {name}" for name in unmatched]
        if warnings:
            lines += ["", _("Warnings:")] + [f"- {w}" for w in warnings]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Tracking list (second format)
    # ------------------------------------------------------------------
    @api.model
    def _consultant_index(self):
        """Field consultants by full name and by first name."""
        group = self.env.ref(CONSULTANT_GROUP).sudo()
        users = group.all_user_ids.filtered(lambda u: u.active and not u.share)
        by_name, by_first = defaultdict(set), defaultdict(set)
        for user in users:
            name = normalize(user.name)
            if name:
                by_name[name].add(user.id)
                by_first[name.split()[0]].add(user.id)
        return dict(by_name), dict(by_first)

    @api.model
    def _match_consultant(self, value, index):
        """The consultant a sheet names, when exactly one user fits."""
        by_name, by_first = index
        text = normalize(value)
        if not text:
            return self.env["res.users"]
        ids = by_name.get(text) or (
            by_first.get(text) if len(text.split()) == 1 else None
        )
        if ids and len(ids) == 1:
            return self.env["res.users"].browse(next(iter(ids)))
        return self.env["res.users"]

    @api.model
    def _row_consultant(self, record, index, by_sheet):
        """The consultant of one row: its own column, else its sheet's title.

        The workbook has one sheet per consultant (``BERTA``, ``DAVID``...),
        not all of them with an assignment column. A value in the column
        always wins, even when it names nobody.
        """
        if record["consultant"]:
            return self._match_consultant(record["consultant"], index)
        sheet = record["sheet"]
        if sheet not in by_sheet:
            by_sheet[sheet] = self._match_consultant(sheet, index)
        return by_sheet[sheet]

    @api.model
    def _planned_visit(self, dates):
        """Latest visit round of a row, at noon so no timezone moves its day."""
        if not dates:
            return False
        return datetime.datetime.combine(max(dates), datetime.time(12, 0))

    def _tracking_definitions(self, groups):
        """Property definitions the rows need, and the missing ones.

        :return: (types by property name, new definitions to append)
        """
        project = self.project_id
        known = {
            prop["name"]: prop["type"]
            for prop in (project.task_properties_definition or [])
        }
        values, labels = defaultdict(list), {}
        for group in groups:
            for prop, value in group["props"].items():
                values[prop].append(value)
                labels.setdefault(prop, group["labels"][prop])
        new = []
        for prop, prop_values in values.items():
            if prop in known:
                continue
            if prop == tracking.ATTEMPTS_PROPERTY[0]:
                prop_type = "integer"
            else:
                prop_type = tracking.property_type(prop_values)
            known[prop] = prop_type
            new.append(
                {
                    "name": prop,
                    "string": labels[prop],
                    "type": prop_type,
                    "view_in_cards": prop
                    in (tracking.VISIT_STATUS[0], tracking.ATTEMPTS_PROPERTY[0]),
                }
            )
        return known, new

    @api.model
    def _task_name_index(self, existing):
        """Tasks already in the phase by name key.

        The checklist names a business by its subdomain and legal name; the
        tracking list only by the name the consultants use. A row naming a
        task of the phase (its title or its business) is that task.
        """
        index = defaultdict(set)
        for task in existing.values():
            for name in (task.name, task.sudo().business_name):
                key = name_key(name)
                if key:
                    index[key].add(task.id)
        return {key: ids for key, ids in index.items()}

    @api.model
    def _match_existing_task(self, record, index):
        """The one task of the phase a row names, exactly or nearly."""
        Task = self.env["project.task"]
        key = name_key(record["trade_name"] or record["legal_name"])
        if not key:
            return Task
        ids = index.get(key)
        if not ids and len(key) >= 4:
            close = difflib.get_close_matches(
                key, list(index), n=2, cutoff=FUZZY_CUTOFF
            )
            ids = index[close[0]] if len(close) == 1 else None
        if ids and len(ids) == 1:
            return Task.browse(next(iter(ids)))
        return Task

    def _group_tracking_rows(self, records, index, existing, consultants):
        """Match every row and fold the rows of one business together.

        :return: (groups in sheet order, review lines)
        """
        groups, review, by_sheet = {}, {}, {}
        task_names = self._task_name_index(existing)
        for record in records:
            display = record["trade_name"]
            company, website, method, reason = self._match_business(record, index)
            prospect = self.env["res.partner"]
            if not company and not reason:
                task = self._match_existing_task(record, task_names)
                if task:
                    company = task.business_company_id
                    prospect = task.business_partner_id if not company else prospect
                    method = "task"
            if not company and not prospect and not reason:
                prospect, reason = self._match_prospect(
                    record, self._known_prospects(existing)
                )
            if reason:
                review.setdefault(display, f"{display} ({record['sheet']}): {reason}")
                continue
            if company:
                key = f"company:{company.id}"
            elif prospect:
                key = f"partner:{prospect.id}"
            else:
                key = "new:%s" % name_key(display)
            # Every sheet naming a consultant adds one: rows of a business
            # on several consultants' sheets assign all of them.
            user = self._row_consultant(record, consultants, by_sheet)
            if key in groups:
                tracking.merge_tracking(groups[key]["record"], record)
                groups[key]["users"] |= user
                continue
            groups[key] = {
                "key": key,
                "record": record,
                "company": company,
                "website": website,
                "method": method or "prospect",
                "users": user,
            }
        for group in groups.values():
            record = group["record"]
            unknown = record["consultant"] and not self._match_consultant(
                record["consultant"], consultants
            )
            group["consultant_text"] = bool(unknown)
            props = dict(record["props"])
            labels = dict(record["labels"])
            if unknown:
                props[tracking.CONSULTANT_PROPERTY[0]] = record["consultant"]
                labels[tracking.CONSULTANT_PROPERTY[0]] = tracking.CONSULTANT_PROPERTY[
                    1
                ]
            if record["dates"]:
                props[tracking.ATTEMPTS_PROPERTY[0]] = len(record["dates"])
                labels[tracking.ATTEMPTS_PROPERTY[0]] = tracking.ATTEMPTS_PROPERTY[1]
            group["props"], group["labels"] = props, labels
            group["planned"] = self._planned_visit(record["dates"])
        return list(groups.values()), list(review.values())

    def _run_tracking_import(self, records, skipped, info, dry_run):
        """Create or update one task per business from the tracking list."""
        self.ensure_one()
        project = self.project_id
        Task = self.env["project.task"].with_context(
            active_test=False, mail_create_nolog=True
        )
        index = self._matching_index(project)
        existing = self._existing_tasks(Task, project)
        groups, review = self._group_tracking_rows(
            records, index, existing, self._consultant_index()
        )
        types, new_definitions = self._tracking_definitions(groups)
        if new_definitions and not dry_run:
            project.task_properties_definition = (
                project.task_properties_definition or []
            ) + new_definitions
        counts = dict.fromkeys(
            (
                "created",
                "updated",
                "subdomain",
                "name",
                "fuzzy",
                "task",
                "prospect",
                "consultant",
                "consultant_text",
                "planned",
            ),
            0,
        )
        unmatched = []
        for group in groups:
            company, record = group["company"], group["record"]
            counts[group["method"]] += 1
            counts["consultant"] += bool(group["users"])
            counts["consultant_text"] += group["consultant_text"]
            counts["planned"] += bool(group["planned"])
            if not company:
                unmatched.append(record["trade_name"])
            task = existing.get(group["key"])
            if company and not task:
                former, _reason = self._match_prospect(
                    record, self._known_prospects(existing)
                )
                task = former and existing.pop(f"partner:{former.id}")
            counts["updated" if task else "created"] += 1
            if dry_run:
                continue
            props = {
                prop: tracking.property_value(value, types[prop])
                for prop, value in group["props"].items()
                if types.get(prop) in ("char", "boolean", "date", "integer")
            }
            task = self._save_tracking_task(Task, task, group, props)
            existing[
                (
                    f"company:{company.id}"
                    if company
                    else f"partner:{task.business_partner_id.id}"
                )
            ] = task
        return self._tracking_summary(
            dry_run,
            len(records),
            skipped,
            len(groups),
            counts,
            [d["string"] for d in new_definitions],
            info,
            unmatched,
            review,
        )

    def _save_tracking_task(self, Task, task, group, props):
        """Write one business of the tracking list on its task.

        Contact fields, the planned date and the assignee only fill what is
        empty (or move the date later): what the consultants changed in the
        task wins over the sheet. Properties take the sheet's values.
        """
        record, company, website = group["record"], group["company"], group["website"]
        standard = {
            "field_visit_address": record["address"],
            "field_visit_phone": record["phone"],
            "field_visit_email": record["email"],
            "field_visit_contact_name": record["contact"],
            "field_visit_zone": record["zone"],
        }
        planned, users = group["planned"], group["users"]
        vals = {}
        if company:
            vals["business_company_id"] = company.id
            vals["field_visit_import_key"] = f"company:{company.id}"
            if website:
                vals["business_website_id"] = website.id
        if task:
            overwrite = self.overwrite_values
            vals.update(
                {
                    name: value
                    for name, value in standard.items()
                    if value and (overwrite or not task[name]) and value != task[name]
                }
            )
            if planned and (
                not task.date_deadline
                or planned > task.date_deadline
                or (overwrite and planned != task.date_deadline)
            ):
                vals["date_deadline"] = planned
            # Assignees are only added: never removed by a re-import.
            if users - task.user_ids:
                vals["user_ids"] = [
                    Command.link(user.id) for user in users - task.user_ids
                ]
            if props:
                vals["task_properties"] = self._merged_properties(
                    task, props, overwrite
                )
            task.write(vals)
        else:
            vals.update({name: value for name, value in standard.items() if value})
            vals.update(
                name=record["trade_name"] or company.name,
                project_id=self.project_id.id,
                user_ids=[Command.set(users.ids)],
            )
            if planned:
                vals["date_deadline"] = planned
            if props:
                vals["task_properties"] = props
            if not company:
                partner = self._prospect_partner(record)
                vals["business_partner_id"] = partner.id
                vals["field_visit_import_key"] = f"partner:{partner.id}"
            task = Task.create(vals)
        self._post_observations(task, record["observations"])
        return task

    def _tracking_summary(
        self,
        dry_run,
        total,
        skipped,
        businesses,
        counts,
        new_properties,
        info,
        unmatched,
        review,
    ):
        _ = self.env._
        lines = [
            _("DRY RUN: nothing was changed.") if dry_run else _("Import finished."),
            _("Format: consultants' tracking list."),
            _("Business rows read: %s", total),
            _("Rows skipped (no name): %s", skipped),
            _("Businesses (rows of several sheets merged): %s", businesses),
            _("Tasks created: %s", counts["created"]),
            _("Tasks updated: %s", counts["updated"]),
            _("Matched by subdomain: %s", counts["subdomain"]),
            _("Matched by exact name: %s", counts["name"]),
            _("Matched by similar name: %s", counts["fuzzy"]),
            _("Matched to a task already in the phase: %s", counts["task"]),
            _("Not on the platform (prospect contacts): %s", counts["prospect"]),
            _("To review (not imported): %s", len(review)),
            _("Assigned to a consultant user: %s", counts["consultant"]),
            _(
                "Consultant kept as text (no matching user): %s",
                counts["consultant_text"],
            ),
            _("With a planned visit date: %s", counts["planned"]),
        ]
        if new_properties:
            joined = ", ".join(new_properties)
            lines.append(
                _("Task fields that would be added: %s", joined)
                if dry_run
                else _("New task fields: %s", joined)
            )
        sheets = info["sheets"]
        if len(sheets) > 1:
            # Rows of one business are merged in sheet order: the first
            # sheet's values win over the next ones.
            lines.append(_("Authoritative sheet (its values win): '%s'", sheets[0][0]))
            largest = max(sheets, key=lambda sheet: sheet[1])
            if largest[1] > sheets[0][1]:
                lines.append(
                    _(
                        "Warning: the authoritative sheet is not the largest one "
                        "('%(largest)s' has %(rows)s rows). Move the master list "
                        "first in the workbook if it is not.",
                        largest=largest[0],
                        rows=largest[1],
                    )
                )
        if info["notes"]:
            lines += ["", _("Sheets:")] + [f"- {note}" for note in info["notes"]]
        if info["ignored"]:
            lines += ["", _("Columns ignored for privacy (never read):")]
            lines += [f"- {column}" for column in info["ignored"]]
        if review:
            lines += [
                "",
                _("To review (fix the sheet or the company, then re-import):"),
            ]
            lines += [f"- {line}" for line in review]
        if unmatched:
            lines += ["", _("Businesses without a platform company:")]
            lines += [f"- {name}" for name in unmatched]
        return "\n".join(lines)
