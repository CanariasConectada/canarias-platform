# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Point the shipped seals at their online courses.

``training_url`` is seeded in ``data/certification_type_data.xml``, but that
file is ``noupdate="1"``: a fresh install gets the links, an upgraded
database does not. Fill them here, and only where nobody set one already.
"""
from odoo import SUPERUSER_ID, api

COURSES = {
    "company_certification.certification_type_silver": (
        "https://canariasconectada.es/slides/silver-economy-3"
    ),
    "company_certification.certification_type_sustainability": (
        "https://canariasconectada.es/slides/sostenibilidad-2"
    ),
}


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid, url in COURSES.items():
        seal = env.ref(xmlid, raise_if_not_found=False)
        if seal and not seal.training_url:
            seal.training_url = url
