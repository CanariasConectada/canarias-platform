# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import io
import unittest
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from ..wizards import field_visit_import
from ..wizards.field_visit_import import name_key, names_agree, subdomain_slug

try:
    import openpyxl
except ImportError:  # pragma: no cover
    openpyxl = None

from .common import FieldVisitCase

needs_openpyxl = unittest.skipUnless(openpyxl, "openpyxl is not installed")

HEADER = [
    "Total ",
    "Anexo ",
    "cantidad  por seccion ",
    "Comercio (razón social)",
    "Nombre comercial",
    "Microsite",
    "Subdominio",
    "Justificados en listado Fase I",
    "Evidencias graficas Fase I ",
    "Compromisos firmados ",
    "Estado Participación",
    "Formación",
    "Declaracion firmada ",
    "Observaciones ",
]


def row(total, legal, trade, subdomain=None, status="Si", notes=None, annex=None):
    return [
        total,
        annex,
        1,
        legal,
        trade,
        "X" if subdomain else None,
        subdomain,
        "Si",
        "No",
        "pendiente",
        status,
        "No",
        None,
        notes,
    ]


@tagged("post_install", "-at_install")
class TestFieldVisitImport(FieldVisitCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.hardware = cls._create_business(
            "Zzfv Ferreteria Central", "zzfv-ferreteria"
        )
        cls.florist = cls._create_business("Zzfv Floristeria del Puerto", "zzfv-flores")
        cls.rows = [
            HEADER,
            ["SECCION 1 "] + [None] * 13,
            # by subdomain; the trade name agrees with the company name
            row(
                1,
                "Some Legal Name SL",
                "Zzfv Bakery",
                " zzfv-bakery-demo ",
                annex=12,
                notes="First visit: owner asked for the brochure",
            ),
            # by exact name once legal form and accents are ignored
            row(2, "ZZFV FERRETERÍA CENTRAL, S.L.", "Ferreteria", None, status="NO"),
            ["ESTÁN CERRADOS "] + [None] * 13,
            # by similar name (one letter off), no subdomain
            row(3, None, "Zzfv Floristeria del Puertos", None, status="Cerrado"),
            ["POTENCIALES ADHESIONES "] + [None] * 13,
            # prospect: only the trade name, unknown status value
            row(4, None, "Zzfv Nuevo Cafe", None, status="Quizas"),
            # stray note under the table: no number in the first column
            [None, None, None, None, "x"] + [None] * 9,
        ]

    def _xlsx(self, rows):
        book = openpyxl.Workbook()
        sheet = book.active
        sheet.title = "Hoja 1"
        for values in rows:
            sheet.append(values)
        buffer = io.BytesIO()
        book.save(buffer)
        return base64.b64encode(buffer.getvalue())

    def _csv(self, rows):
        lines = [";".join("" if v is None else str(v) for v in r) for r in rows]
        return base64.b64encode("\n".join(lines).encode())

    def _import(self, rows=None, dry_run=False, project=None, **extra):
        wizard = self.env["project.field.visit.import"].create(
            dict(
                {
                    "project_id": (project or self.project).id,
                    "file": self._xlsx(rows or self.rows),
                    "filename": "phase1.xlsx",
                    "dry_run": dry_run,
                },
                **extra,
            )
        )
        wizard.action_import()
        return wizard

    def _props(self, task):
        """Stored checklist values (the record attribute gives labels)."""
        return {
            p["name"]: p.get("value")
            for p in task.read(["task_properties"])[0]["task_properties"]
        }

    def _tasks(self, project=None):
        return self.env["project.task"].search(
            [("project_id", "=", (project or self.project).id)]
        )

    def test_helpers(self):
        self.assertEqual(
            name_key(" ZZFV Ferretería  Central, S.L. "), "zzfv ferreteria central"
        )
        self.assertEqual(name_key("Bar Pepe SLU"), "bar pepe")
        self.assertEqual(subdomain_slug("https://Shop.canariasconectada.es/"), "shop")
        self.assertEqual(subdomain_slug(" shop "), "shop")

    @needs_openpyxl
    def test_dry_run_changes_nothing(self):
        project = self.env["project.project"].create(
            {"name": "Zzfv empty phase", "is_field_visit_project": True}
        )
        wizard = self._import(dry_run=True, project=project)
        self.assertIn("Tasks created: 4", wizard.summary)
        self.assertIn("Matched by subdomain: 1", wizard.summary)
        self.assertIn("Matched by exact name: 1", wizard.summary)
        self.assertIn("Matched by similar name: 1", wizard.summary)
        self.assertIn("prospect contacts): 1", wizard.summary)
        self.assertIn("Rows skipped (no number or no name): 1", wizard.summary)
        self.assertFalse(self._tasks(project))
        self.assertFalse(project.type_ids)
        self.assertFalse(project.task_properties_definition)

    @needs_openpyxl
    def test_import_matches_and_fills_checklist(self):
        wizard = self._import()
        tasks = self._tasks()
        self.assertEqual(len(tasks), 4)
        by_company = {t.business_company_id: t for t in tasks}
        bakery = by_company[self.business]
        self.assertEqual(
            bakery.business_website_id.domain, "https://zzfv-bakery-demo.example.com"
        )
        self.assertEqual(bakery.stage_id.name, "Seccion 1")
        self.assertEqual(
            self._props(bakery),
            {
                "annex_number": 12,
                "microsite": True,
                "justified_list": "yes",
                "graphic_evidence": "no",
                "commitment_signed": "pending",
                "participation_status": "yes",
                "training": "no",
                "declaration_signed": None,
            },
        )
        self.assertIn(self.hardware, by_company)
        florist = by_company[self.florist]
        self.assertEqual(florist.stage_id.name, "Están cerrados")
        self.assertEqual(
            self._props(florist)["participation_status"],
            "closed",
        )
        prospect = tasks.filtered(lambda t: not t.business_company_id)
        self.assertEqual(prospect.name, "Zzfv Nuevo Cafe")
        self.assertEqual(prospect.business_partner_id.name, "Zzfv Nuevo Cafe")
        self.assertTrue(prospect.business_partner_id.is_company)
        self.assertEqual(prospect.stage_id.name, "Potenciales adhesiones")
        self.assertIn("Quizas", wizard.summary)
        self.assertIn("Zzfv Nuevo Cafe", wizard.summary)
        notes = bakery.message_ids.filtered(lambda m: "brochure" in (m.body or ""))
        self.assertEqual(len(notes), 1)

    @needs_openpyxl
    def test_reimport_is_idempotent(self):
        self._import()
        tasks = self._tasks()
        messages = tasks.message_ids
        bakery = tasks.filtered(lambda t: t.business_company_id == self.business)
        bakery.stage_id = self.stage  # moved by a consultant
        wizard = self._import()
        self.assertEqual(self._tasks(), tasks)
        self.assertIn("Tasks updated: 4", wizard.summary)
        self.assertEqual(tasks.message_ids, messages, "no duplicated notes")
        self.assertEqual(bakery.stage_id, self.stage, "consultant's stage kept")
        # A new observation is posted once; the stage follows only on request.
        rows = [list(r) for r in self.rows]
        rows[2][13] = "Second visit: brochure delivered"
        self._import(rows=rows, update_stages=True)
        self.assertEqual(len(bakery.message_ids - messages), 1)
        self.assertEqual(bakery.stage_id.name, "Seccion 1")
        self.assertEqual(
            len(self.project.type_ids.filtered(lambda s: s.name == "Seccion 1")), 1
        )

    @needs_openpyxl
    def test_prospect_keeps_its_task_when_it_joins(self):
        self._import()
        prospect = self._tasks().filtered(lambda t: not t.business_company_id)
        company = self._create_business("Zzfv Nuevo Cafe", "zzfv-nuevo-cafe")
        self._import()
        self.assertEqual(len(self._tasks()), 4)
        self.assertEqual(prospect.business_company_id, company)
        self.assertEqual(prospect.business_partner_id, company.partner_id)

    @needs_openpyxl
    def test_existing_phase_fields_are_respected(self):
        project = self.env["project.project"].create(
            {"name": "Zzfv phase II", "is_field_visit_project": True}
        )
        project.task_properties_definition = [
            {
                "name": "training",
                "string": "Training",
                "type": "selection",
                "selection": [["yes", "Yes"], ["no", "No"], ["pending", "Pending"]],
            },
        ]
        self._import(project=project)
        self.assertEqual(len(project.task_properties_definition), 1)
        values = [self._props(t) for t in self._tasks(project)]
        self.assertEqual(values, [{"training": "no"}] * 4)

    def test_csv_fallback(self):
        wizard = self.env["project.field.visit.import"].create(
            {
                "project_id": self.project.id,
                "file": self._csv(self.rows[:4]),
                "filename": "phase1.csv",
                "dry_run": True,
            }
        )
        wizard.action_import()
        # CSV cells are text: the numbered rows still count as businesses.
        self.assertIn("Business rows read: 2", wizard.summary)

    def test_create_phase_project(self):
        wizard = self.env["project.field.visit.import"].create(
            {"new_project_name": "Zzfv Consultoria - Fase II"}
        )
        wizard.action_create_phase_project()
        self.assertTrue(wizard.project_id.is_field_visit_project)
        self.assertEqual(len(wizard.project_id.task_properties_definition), 8)

    def test_names_agree(self):
        self.assertTrue(names_agree(["zzfv bakery"], "zzfv bakery demo"))
        self.assertTrue(names_agree(["zzfv bakeri demo"], "zzfv bakery demo"))
        self.assertFalse(names_agree(["other shop"], "zzfv bakery demo"))
        self.assertFalse(names_agree(["zzfv"], "zzfv bakery demo"), "too short")

    def _wizard(self, rows, **extra):
        return self.env["project.field.visit.import"].create(
            dict(
                {
                    "project_id": self.project.id,
                    "file": self._csv(rows),
                    "filename": "phase1.csv",
                    "dry_run": False,
                },
                **extra,
            )
        )

    def test_missing_openpyxl_asks_for_csv(self):
        wizard = self.env["project.field.visit.import"].create(
            {
                "project_id": self.project.id,
                "file": base64.b64encode(b"PK not really a workbook"),
                "filename": "phase1.xlsx",
            }
        )
        with patch.object(field_visit_import, "openpyxl", None):
            with self.assertRaisesRegex(UserError, "openpyxl"):
                wizard.action_import()

    def test_limits(self):
        with patch.object(field_visit_import, "MAX_FILE_BYTES", 100):
            with self.assertRaisesRegex(UserError, "larger than"):
                self._wizard(self.rows).action_import()
        with patch.object(field_visit_import, "MAX_ROWS", 3):
            with self.assertRaisesRegex(UserError, "more than"):
                self._wizard(self.rows).action_import()
        wide = [HEADER + ["extra"] * 50]
        with self.assertRaisesRegex(UserError, "more than"):
            self._wizard(wide).action_import()

    @needs_openpyxl
    def test_xlsx_limits_before_reading(self):
        with patch.object(field_visit_import, "MAX_ROWS", 3):
            with self.assertRaisesRegex(UserError, "more than"):
                self._import()
        wide = [HEADER + ["extra"] * 50]
        with self.assertRaisesRegex(UserError, "more than"):
            self._import(rows=wide)

    def test_only_field_managers_import(self):
        wizard = self._wizard(self.rows)
        for user in (self.consultant, self.project_manager):
            with self.assertRaises(AccessError):
                wizard.with_user(user).action_import()

    def test_excluded_candidates(self):
        """Portal, zone, archived and owning companies are never visited."""
        main = self.env.ref("base.main_company")
        # A company with a website cannot be archived: a plain one then.
        archived = self.env["res.company"].create({"name": "Zzfv Archived Shop"})
        archived.active = False
        rows = [
            HEADER,
            row(1, None, main.name, None),
            row(2, None, "Zzfv Archived Shop", None),
        ]
        zone = self.env["res.company"]
        if "zone_company_key" in zone._fields:
            zone = zone.search([("zone_company_key", "!=", False)], limit=1)
        if zone:
            rows.append(row(3, None, zone.name, None))
        wizard = self._wizard(rows, dry_run=True)
        wizard.action_import()
        self.assertIn("Matched by subdomain: 0", wizard.summary)
        self.assertIn("Matched by exact name: 0", wizard.summary)
        self.assertIn("Matched by similar name: 0", wizard.summary)
        self.assertIn("To review (not imported): 1", wizard.summary)
        self.assertIn("matches an archived company", wizard.summary)

    def test_subdomain_needs_agreeing_name(self):
        wizard = self._wizard(
            [HEADER, row(1, "Somebody Else SL", "Unrelated Shop", "zzfv-bakery-demo")]
        )
        wizard.action_import()
        self.assertIn("To review (not imported): 1", wizard.summary)
        self.assertIn("does not match", wizard.summary)
        self.assertFalse(self._tasks())

    def test_shared_slug_goes_to_review(self):
        other = self._create_business("Zzfv Twin Shop", "zzfv-twin")
        self.env["website"].search(
            [("company_id", "=", other.id)]
        ).domain = "https://zzfv-bakery-demo.example.org"
        wizard = self._wizard([HEADER, row(1, None, "Zzfv Bakery", "zzfv-bakery-demo")])
        wizard.action_import()
        self.assertIn("several websites", wizard.summary)
        self.assertFalse(self._tasks())

    def test_existing_task_by_business_is_reused(self):
        manual = self.env["project.task"].create(
            {
                "name": "Created by hand",
                "project_id": self.project.id,
                "business_company_id": self.business.id,
            }
        )
        self._wizard(
            [HEADER, row(1, None, "Zzfv Bakery", "zzfv-bakery-demo")]
        ).action_import()
        self.assertEqual(self._tasks(), manual)

    def test_renamed_prospect_keeps_its_task(self):
        self._wizard([HEADER, row(1, None, "Zzfv Nuevo Cafe")]).action_import()
        task = self._tasks()
        partner = task.business_partner_id
        self.assertTrue(partner.is_field_visit_prospect)
        self.assertEqual(partner.field_visit_prospect_key, "zzfv nuevo cafe")
        # One letter off: surely the same business.
        self._wizard([HEADER, row(1, None, "Zzfv Nuevo Cafes")]).action_import()
        self.assertEqual(self._tasks(), task)
        self.assertEqual(task.business_partner_id, partner)
        # Renamed further: not sure, the manager decides.
        wizard = self._wizard([HEADER, row(1, None, "Zzfv Nuevo Cafe Bar")])
        wizard.action_import()
        self.assertIn("To review (not imported): 1", wizard.summary)
        self.assertEqual(self._tasks(), task)

    def test_same_named_prospects_with_different_annex(self):
        rows = [
            HEADER,
            row(1, None, "Zzfv Kiosko", annex=101),
            row(2, None, "Zzfv Kiosko", annex=202),
        ]
        self._wizard(rows).action_import()
        tasks = self._tasks()
        self.assertEqual(len(tasks), 2)
        self.assertEqual(
            sorted(tasks.business_partner_id.mapped("field_visit_annex_number")),
            [101, 202],
        )
        wizard = self._wizard(rows)
        wizard.action_import()
        self.assertEqual(self._tasks(), tasks)
        self.assertIn("Tasks updated: 2", wizard.summary)
