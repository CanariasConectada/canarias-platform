# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import io

import openpyxl

from odoo.tests import tagged

from ..wizards.field_visit_import import name_key, subdomain_slug
from .common import FieldVisitCase

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
            # by subdomain, whatever the names say
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

    def test_prospect_keeps_its_task_when_it_joins(self):
        self._import()
        prospect = self._tasks().filtered(lambda t: not t.business_company_id)
        company = self._create_business("Zzfv Nuevo Cafe", "zzfv-nuevo-cafe")
        self._import()
        self.assertEqual(len(self._tasks()), 4)
        self.assertEqual(prospect.business_company_id, company)
        self.assertEqual(prospect.business_partner_id, company.partner_id)

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
        lines = [
            ";".join("" if v is None else str(v) for v in r) for r in self.rows[:4]
        ]
        wizard = self.env["project.field.visit.import"].create(
            {
                "project_id": self.project.id,
                "file": base64.b64encode("\n".join(lines).encode()),
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
