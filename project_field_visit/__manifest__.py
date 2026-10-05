# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Project Field Visits",
    "summary": "Door-to-door consultant visits to the platform businesses, "
    "one project per phase with its own checklist fields",
    "version": "19.0.1.4.0",
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "category": "Services/Project",
    "license": "AGPL-3",
    "development_status": "Beta",
    # ``website`` for the microsite of each business (one website per
    # company on this platform); ``project`` carries the native task
    # properties that hold the per-phase checklist;
    # ``partner_microsite_manager`` says what each microsite still lacks.
    "depends": ["project", "website", "partner_microsite_manager"],
    "data": [
        "security/field_visit_security.xml",
        "security/ir.model.access.csv",
        "data/field_visit_message_templates.xml",
        "data/field_visit_activity_data.xml",
        "data/field_visit_microsite_status.xml",
        "wizards/field_visit_log_views.xml",
        "wizards/field_visit_import_views.xml",
        "views/project_project_views.xml",
        "views/project_task_views.xml",
        "views/res_company_views.xml",
        "views/res_partner_views.xml",
        "views/menus.xml",
        "data/field_visit_admin_access.xml",
    ],
    "installable": True,
    "application": False,
}
