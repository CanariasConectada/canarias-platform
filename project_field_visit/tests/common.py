# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase


class FieldVisitCase(TransactionCase):
    """A phase project owned by the programme company, a business company
    with its microsite, and a consultant who only belongs to the programme.

    Names carry a ``zzfv`` marker so they never collide with the businesses
    already present in the validation database.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.owner = cls.env.company
        cls.business = cls._create_business("Zzfv Bakery Demo", "zzfv-bakery-demo")
        cls.project = cls.env["project.project"].create(
            {
                "name": "Zzfv door to door - Phase I",
                "is_field_visit_project": True,
                "company_id": cls.owner.id,
                "privacy_visibility": "employees",
            }
        )
        cls.project._field_visit_ensure_properties()
        cls.stage = cls.env["project.task.type"].create(
            {"name": "Zzfv visited", "project_ids": [(4, cls.project.id)]}
        )
        cls.consultant = cls.env["res.users"].create(
            {
                "name": "Zzfv Consultant",
                "login": "zzfv_consultant",
                "email": "zzfv.consultant@example.com",
                "company_id": cls.owner.id,
                "company_ids": [(6, 0, cls.owner.ids)],
                "group_ids": [(6, 0, [cls.env.ref("project.group_project_user").id])],
            }
        )

    @classmethod
    def _create_business(cls, name, slug):
        company = cls.env["res.company"].create({"name": name})
        website = cls.env["website"].search([("company_id", "=", company.id)], limit=1)
        if not website:
            website = cls.env["website"].create(
                {"name": name, "company_id": company.id}
            )
        website.domain = f"https://{slug}.example.com"
        return company
