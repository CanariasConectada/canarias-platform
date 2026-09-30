# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Backfill the hero and sponsor images of the seeded content types.

The two legacy verticals are seeded inside a ``noupdate="1"`` block, so the
new ``hero_image`` / ``hero_subtitle`` / ``sponsor_logo`` / ``sponsor_name``
values added to ``data/local_content_type_data.xml`` only reach fresh
installs. Existing databases get them here, and only where the field is
still empty so an admin's own artwork is never overwritten.
"""
import base64
import logging

from odoo import SUPERUSER_ID, api
from odoo.tools.misc import file_path

_logger = logging.getLogger(__name__)

HERO_IMAGE = "website_local_content/static/src/img/hero-cine-astoria.jpg"
SPONSOR_LOGO = "website_local_content/static/src/img/logo-gobierno-canarias.png"
HERO_SUBTITLE = "Discover and share the stories of the neighbourhood"
SPONSOR_NAME = "Gobierno de Canarias"


def _read_image(resource):
    with open(file_path(resource), "rb") as image_file:
        return base64.b64encode(image_file.read())


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    hero_image = _read_image(HERO_IMAGE)
    updates = {
        "website_local_content.content_type_living_memory": {
            "hero_image": hero_image,
            "hero_subtitle": HERO_SUBTITLE,
            "sponsor_logo": _read_image(SPONSOR_LOGO),
            "sponsor_name": SPONSOR_NAME,
        },
        "website_local_content.content_type_places_of_interest": {
            "hero_image": hero_image,
            "hero_subtitle": HERO_SUBTITLE,
        },
    }
    for xmlid, values in updates.items():
        content_type = env.ref(xmlid, raise_if_not_found=False)
        if not content_type:
            continue
        missing = {
            field: value
            for field, value in values.items()
            if not content_type[field]
        }
        if missing:
            content_type.write(missing)
            _logger.info(
                "website_local_content: seeded %s on %s.",
                ", ".join(sorted(missing)),
                xmlid,
            )
