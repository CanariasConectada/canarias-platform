# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import datetime
import io
import unittest
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged

from ..wizards.field_visit_tracking import tracking_layout

try:
    import openpyxl
except ImportError:  # pragma: no cover
    openpyxl = None

from .common import CONSULTANT, FieldVisitCase

MANAGER = "project_field_visit.group_field_visit_manager"


def workbook(sheets):
    """xlsx bytes (base64) of ``[(title, rows), ...]``."""
    book = openpyxl.Workbook()
    book.remove(book.active)
    for title, rows in sheets:
        sheet = book.create_sheet(title)
        for values in rows:
            sheet.append(values)
    buffer = io.BytesIO()
    book.save(buffer)
    return base64.b64encode(buffer.getvalue())


@tagged("post_install", "-at_install")
@unittest.skipUnless(openpyxl, "openpyxl is not installed")
class TestFieldVisitTracking(FieldVisitCase):
    """A synthetic workbook shaped like the consultants' tracking list:
    a master sheet, a consultant's sheet, a meeting calendar with addresses,
    a sheet of visit rounds, one without a name header and one with
    credentials. No client data."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.hardware = cls._create_business(
            "Zzfv Ferreteria Central", "zzfv-ferreteria"
        )
        cls.consultant.name = "Zzfvberta Consultant"
        cls.soon = fields.Date.today() + datetime.timedelta(days=10)
        cls.past = [datetime.datetime(2026, 7, d) for d in (1, 13, 24)]
        cls.sheets = [
            (
                "MASTER ",
                [
                    [
                        "f",
                        None,
                        "Nombre",
                        "ZONA",
                        "Canarias Conectada",
                        "CITA ",
                        "CORREOS",
                        "TLF",
                        "MICROSITE",
                    ],
                    [
                        1.0,
                        True,
                        "ZZFV BAKERY DEMO",
                        "G",
                        "SI",
                        "FORMADO ",
                        "Owner@Zzfv-Bakery.example.com",
                        928000001.0,
                        "SI",
                    ],
                    [
                        2.0,
                        False,
                        "Zzfv Ferreteria Central S.L.",
                        "FG",
                        "PENDIENTE",
                        None,
                        None,
                        "600 000 002",
                        "NO",
                    ],
                    [
                        3.0,
                        False,
                        "Zzfv Tienda Nueva",
                        "TyL",
                        "posible adhesion",
                        "NO",
                        None,
                        None,
                        None,
                    ],
                    [None, None, None, None, "FORMADO", None, None, None, None],
                ],
            ),
            (
                "BERTA",
                [
                    [None, None, "Nombre", "ZONA", "ASIGNACION ", "TLF"],
                    [1.0, True, "Zzfv Bakery Demo", "X", "ZZFVBERTA", "699 999 999"],
                    [2.0, True, "Zzfv Ferreteria Central", "FG", "IRENE", None],
                ],
            ),
            (
                "contraseñas ",
                [
                    ["Email", "NOMBRE", "MAIL", "Password"],
                    ["x", "Zzfv Secret Shop", "a@b.c", "hunter2"],
                ],
            ),
            (
                "SANTIAGO ",
                [
                    [None, "legend", "http://example.com"],
                    [],
                    [
                        "Fecha de la reunión",
                        "Hora",
                        "Categoría",
                        "Descripción",
                        "DIRECCIÓN ",
                        "NOMBRE ",
                        "MAIL ",
                        "Notas",
                        "Alta usuario ",
                    ],
                    [
                        datetime.datetime.combine(cls.soon, datetime.time()),
                        datetime.time(9, 30),
                        "presencial",
                        "Zzfv Bakery Demo",
                        "Calle Mayor 1, Las Palmas",
                        "Ana",
                        "ana@example.com",
                        "Bring the poster",
                        True,
                    ],
                ],
            ),
            (
                "los que faltan",
                [
                    [None, None, None, "CITA", "DIA", "OBSERVACIONES "],
                    [1.0, True, "Zzfv Tienda Nueva", "SI", None, "never read"],
                ],
            ),
            (
                "rondas",
                [
                    ["Nombre", "ZONA", "DIA", "2ªvuelta", "3ªvuelta", "SE LLAMA "],
                    ["Zzfv Ferreteria Central", "FG", *cls.past, "SI"],
                ],
            ),
        ]

    def _import(self, sheets=None, dry_run=False):
        wizard = self.env["project.field.visit.import"].create(
            {
                "project_id": self.project.id,
                "file": workbook(sheets or self.sheets),
                "filename": "listado.xlsx",
                "dry_run": dry_run,
            }
        )
        wizard.action_import()
        return wizard

    def _tasks(self):
        return self.env["project.task"].search([("project_id", "=", self.project.id)])

    def _props(self, task):
        return {
            p["name"]: p.get("value")
            for p in task.read(["task_properties"])[0]["task_properties"]
        }

    def _reminders(self, task):
        activity_type = self.env.ref(
            "project_field_visit.mail_activity_type_field_visit"
        )
        return task.activity_ids.filtered(lambda a: a.activity_type_id == activity_type)

    def test_layout_detection(self):
        layout = tracking_layout(
            ["Fecha de la reunión", "Descripción", "DIRECCIÓN ", "NOMBRE ", "TLF"]
        )
        self.assertEqual(layout["name"], 1, "the specific business column wins")
        self.assertEqual(layout["contact"], 3, "a plain 'Nombre' is then a person")
        self.assertEqual(layout["address"], 2)
        self.assertEqual(list(layout["dates"]), [0])
        self.assertTrue(tracking_layout(["Email", "NOMBRE", "Password"])["secret"])
        self.assertIsNone(tracking_layout(["CITA", "DIA", "OBSERVACIONES"]))
        # "mail cita" is a follow-up column, not the business e-mail.
        layout = tracking_layout(["Nombre", "ZONA", "mail cita "])
        self.assertNotIn("email", layout)
        self.assertEqual(list(layout["props"].values())[0][0], "fv_mailcita")

    def test_dry_run_changes_nothing(self):
        definition = self.project.task_properties_definition
        wizard = self._import(dry_run=True)
        summary = wizard.summary
        self.assertIn("Format: consultants' tracking list.", summary)
        self.assertIn("Businesses (rows of several sheets merged): 3", summary)
        self.assertIn("Tasks created: 3", summary)
        self.assertIn("Matched by exact name: 2", summary)
        self.assertIn("Not on the platform (prospect contacts): 1", summary)
        self.assertIn("Assigned to a consultant user: 1", summary)
        self.assertIn("Consultant kept as text (no matching user): 1", summary)
        self.assertIn("Sheet 'contraseñas ' skipped: it holds credentials.", summary)
        self.assertIn("Sheet 'los que faltan' skipped", summary)
        self.assertIn("Estado de visita", summary)
        self.assertNotIn("Zzfv Secret Shop", summary)
        self.assertIn("Authoritative sheet (its values win): 'MASTER '", summary)
        self.assertNotIn("not the largest one", summary)
        self.assertFalse(self._tasks())
        self.assertEqual(self.project.task_properties_definition, definition)

    def test_import_fills_the_task(self):
        self._import()
        tasks = self._tasks()
        self.assertEqual(len(tasks), 3)
        bakery = tasks.filtered(lambda t: t.business_company_id == self.business)
        # Master sheet first; the other sheets fill what it leaves empty.
        self.assertEqual(bakery.field_visit_zone, "G")
        self.assertEqual(bakery.field_visit_phone, "928000001")
        self.assertEqual(bakery.field_visit_email, "owner@zzfv-bakery.example.com")
        self.assertEqual(bakery.field_visit_address, "Calle Mayor 1, Las Palmas")
        self.assertEqual(bakery.field_visit_contact_name, "Ana")
        self.assertEqual(
            bakery.field_visit_map_url,
            "https://www.google.com/maps/search/?api=1&query="
            "Calle+Mayor+1%2C+Las+Palmas",
        )
        self.assertEqual(bakery.user_ids, self.consultant)
        self.assertEqual(bakery.date_deadline.date(), self.soon)
        props = self._props(bakery)
        self.assertEqual(props["fv_visit_status"], "FORMADO")
        self.assertEqual(props["fv_canariasconectada"], "SI")
        self.assertEqual(props["fv_categoria"], "presencial")
        self.assertIs(props["fv_altausuario"], True)
        self.assertEqual(props["fv_hours"], "09:30")
        self.assertEqual(props["fv_contact_attempts"], 1)
        self.assertEqual(
            len(bakery.message_ids.filtered(lambda m: "poster" in (m.body or ""))), 1
        )
        reminder = self._reminders(bakery)
        self.assertEqual(reminder.user_id, self.consultant)
        self.assertEqual(reminder.date_deadline, self.soon)

        hardware = tasks.filtered(lambda t: t.business_company_id == self.hardware)
        self.assertFalse(hardware.user_ids)
        self.assertEqual(self._props(hardware)["fv_consultant"], "IRENE")
        self.assertEqual(self._props(hardware)["fv_contact_attempts"], 3)
        self.assertEqual(hardware.date_deadline, self.past[-1].replace(hour=12))
        self.assertFalse(self._reminders(hardware), "no reminder in the past")

        prospect = tasks - bakery - hardware
        self.assertTrue(prospect.business_partner_id.is_field_visit_prospect)
        self.assertEqual(prospect.field_visit_zone, "TyL")
        types = {p["name"]: p["type"] for p in self.project.task_properties_definition}
        self.assertEqual(types["fv_altausuario"], "boolean")
        self.assertEqual(types["fv_contact_attempts"], "integer")
        self.assertEqual(types["fv_visit_status"], "char")
        self.assertIn("training", types, "the phase I checklist is kept")

    def test_reimport_keeps_consultant_changes(self):
        self._import()
        bakery = self._tasks().filtered(
            lambda t: t.business_company_id == self.business
        )
        # Typed in Odoo by the consultants after the first import.
        bakery.field_visit_phone = "611 111 111"
        bakery.task_properties = dict(
            self._props(bakery), training="yes", fv_visit_status="VISITADO"
        )
        messages = self._tasks().message_ids
        wizard = self._import()
        self.assertIn("Tasks updated: 3", wizard.summary)
        self.assertEqual(len(self._tasks()), 3)
        self.assertEqual(self._tasks().message_ids, messages, "no duplicated notes")
        self.assertEqual(bakery.field_visit_phone, "611 111 111")
        self.assertEqual(self._props(bakery)["training"], "yes")
        self.assertEqual(
            self._props(bakery)["fv_visit_status"], "VISITADO", "edit survives"
        )
        self.assertEqual(len(self._reminders(bakery)), 1)
        # The manager explicitly lets the sheet win.
        wizard = self.env["project.field.visit.import"].create(
            {
                "project_id": self.project.id,
                "file": workbook(self.sheets),
                "filename": "listado.xlsx",
                "dry_run": False,
                "overwrite_values": True,
            }
        )
        wizard.action_import()
        self.assertEqual(self._props(bakery)["fv_visit_status"], "FORMADO")
        self.assertEqual(bakery.field_visit_phone, "928000001")
        self.assertEqual(self._props(bakery)["training"], "yes", "not in the sheet")

    def test_reminder_follows_date_and_assignees(self):
        task = self.env["project.task"].create(
            {
                "name": "Zzfv reminder",
                "project_id": self.project.id,
                "user_ids": [(6, 0, self.consultant.ids)],
                "date_deadline": datetime.datetime.combine(
                    self.soon, datetime.time(12)
                ),
            }
        )
        self.assertEqual(self._reminders(task).date_deadline, self.soon)
        later = self.soon + datetime.timedelta(days=3)
        task.date_deadline = datetime.datetime.combine(later, datetime.time(12))
        self.assertEqual(self._reminders(task).date_deadline, later)
        task.user_ids = False
        self.assertFalse(self._reminders(task))
        # Logging a visit with the next date plans it and assigns the visitor.
        self.env["project.field.visit.log"].with_user(self.consultant).create(
            {
                "task_id": task.id,
                "outcome": "appointment",
                "next_visit_date": datetime.datetime.combine(
                    self.soon, datetime.time(10)
                ),
            }
        ).action_log_visit()
        self.assertEqual(task.user_ids, self.consultant)
        self.assertEqual(self._reminders(task).date_deadline, self.soon)
        # The visit happened, nothing planned: the reminder goes away.
        self.env["project.field.visit.log"].with_user(self.consultant).create(
            {"task_id": task.id, "outcome": "visited"}
        ).action_log_visit()
        self.assertFalse(self._reminders(task))
        # A task outside the field-visit projects never gets one.
        other = self.env["project.task"].create(
            {
                "name": "Zzfv plain task",
                "project_id": self.env["project.project"]
                .create({"name": "Zzfv plain"})
                .id,
                "user_ids": [(6, 0, self.consultant.ids)],
                "date_deadline": datetime.datetime.combine(
                    self.soon, datetime.time(12)
                ),
            }
        )
        self.assertFalse(self._reminders(other))

    def test_admins_become_managers_once(self):
        group = self.env.ref(MANAGER)
        admin = self.env["res.users"].create(
            {
                "name": "Zzfv platform admin",
                "login": "zzfv_platform_admin",
                "group_ids": [(6, 0, self.env.ref("base.group_system").ids)],
            }
        )
        builtin = self.env.ref("base.user_root") | self.env.ref("base.user_admin")
        appointed = group.user_ids - builtin
        if appointed:
            # The validation database may have managers already: the step
            # must then leave the new administrator alone.
            self.assertFalse(self.env["project.project"]._field_visit_grant_admins())
            self.assertNotIn(admin, group.user_ids)
            group.user_ids -= appointed
        granted = self.env["project.project"]._field_visit_grant_admins()
        self.assertIn(admin, granted)
        self.assertIn(admin, group.user_ids)
        self.assertTrue(
            admin.has_group("project_field_visit.group_field_visit_consultant")
        )
        # Somebody now runs the programme: a later administrator is not added.
        other = self.env["res.users"].create(
            {
                "name": "Zzfv second admin",
                "login": "zzfv_second_admin",
                "group_ids": [(6, 0, self.env.ref("base.group_system").ids)],
            }
        )
        self.assertFalse(self.env["project.project"]._field_visit_grant_admins())
        self.assertNotIn(other, group.user_ids)

    def _consultant(self, name, login):
        return self.env["res.users"].create(
            {
                "name": name,
                "login": login,
                "company_id": self.owner.id,
                "company_ids": [(6, 0, self.owner.ids)],
                "group_ids": [(6, 0, self.env.ref(CONSULTANT).ids)],
            }
        )

    def test_assignment_by_sheet_title(self):
        """One sheet per consultant: the title assigns the rows without a
        value in the assignment column; the column wins when filled."""
        ana = self._consultant("Zzfvana Lopez", "zzfv_ana")
        luis = self._consultant("Zzfvluís Pérez", "zzfv_luis")
        sheets = [
            (
                "MASTER",
                [
                    ["Nombre", "ZONA", "TLF"],
                    ["Zzfv Bakery Demo", "G", "600"],
                    ["Zzfv Ferreteria Central", "FG", "601"],
                ],
            ),
            (
                "ZZFVANA",
                [
                    ["Nombre", "ZONA", "ASIGNACION"],
                    ["Zzfv Bakery Demo", "G", None],
                    ["Zzfv Ferreteria Central", "FG", "zzfvluis"],
                ],
            ),
            # No assignment column at all, accents and case differ.
            ("Zzfvluis ", [["Nombre", "ZONA", "TLF"], ["Zzfv Bakery Demo", "G", "6"]]),
        ]
        wizard = self._import(sheets=sheets)
        self.assertIn("Assigned to a consultant user: 2", wizard.summary)
        tasks = self._tasks()
        bakery = tasks.filtered(lambda t: t.business_company_id == self.business)
        hardware = tasks - bakery
        self.assertEqual(bakery.user_ids, ana | luis, "every sheet adds its own")
        self.assertEqual(hardware.user_ids, luis, "the column wins over the title")
        # Re-import: assignees are only ever added.
        hardware.user_ids = [(4, self.consultant.id)]
        self._import(sheets=sheets)
        self.assertEqual(hardware.user_ids, luis | self.consultant)

    def test_sheet_titles_that_assign_nobody(self):
        """Shared first name, inactive user, unknown title, and a column
        naming nobody next to a title that matches: nobody is assigned and
        the dry run says why, sheet by sheet."""
        self._consultant("Zzfvmar One", "zzfv_mar1")
        self._consultant("Zzfvmar Two", "zzfv_mar2")
        self._consultant("Zzfvpia Off", "zzfv_pia").active = False
        luis = self._consultant("Zzfvluis Perez", "zzfv_luis")
        head = ["Nombre", "ZONA", "ASIGNACION"]
        sheets = [
            ("MASTER", [head, ["Zzfv Bakery Demo", "G", None]]),
            ("ZZFVMAR", [head, ["Zzfv Bakery Demo", "G", None]]),
            ("Zzfvpia", [head, ["Zzfv Ferreteria Central", "FG", None]]),
            ("Zzfvluis", [head, ["Zzfv Ferreteria Central", "FG", "Zzfvnadie"]]),
            ("ZONA NORTE", [head, ["Zzfv Bakery Demo", "G", None]]),
        ]
        summary = self._import(sheets=sheets, dry_run=True).summary
        self.assertIn("- 'ZZFVMAR' -> ambiguous (2 users)", summary)
        self.assertIn("- 'Zzfvpia' -> no user", summary)
        self.assertIn(f"- 'Zzfvluis' -> {luis.name}", summary)
        self.assertIn("- 'ZONA NORTE' -> no user", summary)
        self.assertIn("Warning: 4 sheet title(s) name no single consultant", summary)
        self.assertIn("Assigned to a consultant user: 0", summary)
        self._import(sheets=sheets)
        tasks = self._tasks()
        self.assertEqual(len(tasks), 2)
        self.assertFalse(tasks.user_ids)
        hardware = tasks.filtered(lambda t: t.business_company_id == self.hardware)
        self.assertEqual(self._props(hardware)["fv_consultant"], "Zzfvnadie")

    def test_same_file_twice_writes_nothing(self):
        self._import()
        tasks = self._tasks()
        assignees = {task.id: task.user_ids for task in tasks}
        Task = type(self.env["project.task"])
        original, written = Task.write, []

        def spy(records, vals):
            if records.filtered(lambda t: t.project_id == self.project):
                written.append(vals)
            return original(records, vals)

        with patch.object(Task, "write", spy):
            self._import()
        self.assertEqual(self._tasks(), tasks)
        self.assertEqual({task.id: task.user_ids for task in tasks}, assignees)
        self.assertEqual(written, [])

    def test_csv_tracking_list(self):
        rows = [
            ["Nombre", "ZONA", "TLF", "Dirección", "DIA", "ASIGNACION"],
            ["Zzfv Bakery Demo", "G", "600", "C/ Uno 2", "01/07/2026", "Zzfvberta"],
        ]
        text = "\n".join(";".join(r) for r in rows)
        wizard = self.env["project.field.visit.import"].create(
            {
                "project_id": self.project.id,
                "file": base64.b64encode(text.encode()),
                "filename": "listado.csv",
                "dry_run": False,
            }
        )
        wizard.action_import()
        task = self._tasks()
        self.assertEqual(task.business_company_id, self.business)
        self.assertEqual(task.field_visit_address, "C/ Uno 2")
        self.assertEqual(task.date_deadline.date(), datetime.date(2026, 7, 1))
        self.assertEqual(task.user_ids, self.consultant)

    def test_row_naming_a_task_of_the_phase(self):
        """The checklist linked the business by subdomain under another name:
        the tracking list names it like the task, not like the company."""
        task = self.env["project.task"].create(
            {
                "name": "Zzfv Pan Rico",
                "project_id": self.project.id,
                "business_company_id": self.business.id,
            }
        )
        wizard = self._import(
            sheets=[
                (
                    "MASTER",
                    [
                        ["Nombre", "ZONA", "TLF"],
                        ["Zzfv Pan Ricos", "G", "600 000 003"],
                    ],
                )
            ]
        )
        self.assertIn("Matched to a task already in the phase: 1", wizard.summary)
        self.assertEqual(self._tasks(), task)
        self.assertEqual(task.field_visit_phone, "600 000 003")

    def test_privacy_columns_are_never_read(self):
        secrets = [
            "Clave de acceso",
            "Contraseña web",
            "Usuario/contraseña",
            "PIN",
            "Password web",
        ]
        private = ["Nº CIF", "DNI/NIE", "NIF/CIF", "N.I.F."]
        sheets = [
            (
                "MASTER",
                [
                    ["Nombre comercial", "ZONA", *private],
                    ["Zzfv Bakery Demo", "G", "B00000001", "00000000T", "X", "Y"],
                ],
            )
        ]
        for i, header in enumerate(secrets):
            sheets.append(
                (
                    f"S{i}",
                    [
                        ["Nombre comercial", "ZONA", header],
                        [f"Zzfv Secret {i}", "G", "hunter2"],
                    ],
                )
            )
        # A credential header ABOVE the table skips the sheet as well.
        sheets.append(
            (
                "logins",
                [
                    ["Usuario", "Contraseña"],
                    ["Nombre comercial", "ZONA", "TLF"],
                    ["Zzfv Secret Above", "G", "600"],
                ],
            )
        )
        wizard = self._import(sheets=sheets)
        summary = wizard.summary
        self.assertIn("Columns ignored for privacy (never read):", summary)
        for i, header in enumerate(secrets):
            self.assertIn(f"- S{i}: {header}", summary)
            self.assertIn(f"Sheet 'S{i}' skipped: it holds credentials.", summary)
        for header in private:
            self.assertIn(f"- MASTER: {header}", summary)
        self.assertIn("- logins: Usuario", summary)
        tasks = self._tasks()
        self.assertEqual(len(tasks), 1)
        self.assertNotIn("Secret", " ".join(tasks.mapped("name")))
        stored = str(tasks.read(["task_properties"])[0]["task_properties"])
        for value in ("B00000001", "00000000T", "hunter2"):
            self.assertNotIn(value, stored)
            self.assertNotIn(value, summary)
        names = [p["string"] for p in self.project.task_properties_definition]
        self.assertFalse(set(names) & set(private + secrets))

    def test_bare_nombre_of_people_is_not_a_business(self):
        sheets = self.sheets + [
            (
                "contactos",
                [
                    ["Nombre", "ZONA", "TLF"],
                    ["Maria Zzfvperez", "G", "600"],
                    ["Juan Zzfvlopez", "G", "601"],
                    ["Zzfv Bakery Demo", "G", "602"],
                ],
            )
        ]
        wizard = self._import(sheets=sheets, dry_run=True)
        self.assertIn("Sheet 'contactos' skipped: no business column", wizard.summary)
        self.assertIn("Sheet 'MASTER ': 3 business rows.", wizard.summary)
        self.assertIn("Businesses (rows of several sheets merged): 3", wizard.summary)

    def test_all_visits_for_managers_only(self):
        menu = self.env.ref("project_field_visit.menu_field_visit_all_visits")
        mine = self.env.ref("project_field_visit.menu_field_visit_my_visits")
        Menu = self.env["ir.ui.menu"]
        visible = Menu.with_user(self.consultant)._visible_menu_ids()
        self.assertIn(mine.id, visible)
        self.assertNotIn(menu.id, visible)
        self.consultant.group_ids = [(4, self.env.ref(MANAGER).id)]
        Menu.env.registry.clear_cache()
        self.assertIn(menu.id, Menu.with_user(self.consultant)._visible_menu_ids())
