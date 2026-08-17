# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

MODULE = "company_facilities"

# The catalogue becomes the three subdivisions the client specified for task
# #87 and confirmed on 2026-08-17. Everything else is archived, never deleted:
# the relations to the shops survive intact, so un-archiving brings a shop's
# choice back exactly as it was.
RETIRED = [
    # Payment, in full.
    "category_payment",
    "facility_card_payment",
    "facility_contactless",
    "facility_mobile_payment",
    "facility_cash_only",
    "facility_invoice_on_request",
    # Getting there, in full: the microsite already has its own Parking block,
    # and the one entry worth keeping moves to Accessibility instead.
    "category_access",
    "facility_nearby_parking",
    "facility_bicycle_parking",
    "facility_bus_stop",
    # Service, in full.
    "category_service",
    "facility_home_delivery",
    "facility_click_and_collect",
    "facility_gift_wrapping",
    "facility_repairs",
    "facility_whatsapp_orders",
    # We speak, in full.
    "category_languages",
    "facility_speaks_spanish",
    "facility_speaks_english",
    "facility_speaks_german",
    "facility_speaks_italian",
    # In the shop: the subdivision is replaced by Comforts, and its entries
    # either move there or go.
    "category_premises",
    "facility_fitting_room",
    "facility_customer_toilet",
    # Accessibility entries the client's own list does not have.
    "facility_assistance_dogs",
    "facility_large_print",
    "facility_staff_assistance",
]

# What the seed file cannot do to a record that already exists, because it is
# `noupdate="1"`: rename it, move it, or change its icon. Reused rather than
# replaced so the shops that ticked them keep their choice.
REMAPPED = {
    "facility_step_free_access": {
        "name": "Step-free entrance",
        "category": "category_accessibility",
        "icon": "fa-sign-in",
        "sequence": 50,
    },
    "facility_accessible_toilet": {
        "name": "Accessible toilet",
        "category": "category_accessibility",
        "icon": "fa-bath",
        "sequence": 30,
    },
    "facility_accessible_parking": {
        "name": "Accessible parking space",
        "category": "category_accessibility",
        "icon": "fa-wheelchair-alt",
        "sequence": 40,
    },
    "facility_free_wifi": {
        "name": "Free wifi",
        "category": "category_comfort",
        "icon": "fa-wifi",
        "sequence": 10,
    },
    "facility_air_conditioning": {
        "name": "Air conditioning",
        "category": "category_comfort",
        "icon": "fa-snowflake-o",
        "sequence": 20,
    },
    "facility_pets_welcome": {
        "name": "Pet friendly",
        "category": "category_family_pets",
        "icon": "fa-paw",
        "sequence": 10,
    },
}


def _ref(env, name):
    return env.ref("%s.%s" % (MODULE, name), raise_if_not_found=False)


def migrate(cr, version):
    """Reshape the catalogue, and switch the block on.

    Three things the data file cannot do on its own. It is `noupdate="1"` --
    renaming an item is the client's to do and an update must not undo it --
    so a record that already exists is untouchable from XML: it cannot be
    renamed, moved to another subdivision, or archived from there.

    Names are written WITHOUT a language context on purpose. That sets the
    en_US source, which is what this module seeds in; the Spanish and the other
    five languages arrive from the .po files, which the loader reads AFTER this
    migration runs. Writing them under a language context instead is what
    destroys the source (2026-08-14, 2134 records).
    """
    env = api.Environment(cr, SUPERUSER_ID, {})

    # ---------------------------------------------------------------- remap
    for xmlid, values in REMAPPED.items():
        record = _ref(env, xmlid)
        category = _ref(env, values["category"])
        if not record or not category:
            continue
        record.write(
            {
                "name": values["name"],
                "category_id": category.id,
                "icon": values["icon"],
                "sequence": values["sequence"],
                "active": True,
            }
        )

    # -------------------------------------------------------------- archive
    archived = 0
    marks = 0
    missing = []
    for xmlid in RETIRED:
        record = _ref(env, xmlid)
        if not record:
            # A typo here leaves an entry live and looks like success. Four of
            # these were wrong the first time round.
            missing.append(xmlid)
            continue
        if not record.active:
            continue
        if record._name == "company.facility":
            cr.execute(
                "SELECT count(*) FROM res_company_facility_rel WHERE facility_id = %s",
                (record.id,),
            )
            marks += cr.fetchone()[0]
        record.active = False
        archived += 1
    _logger.info(
        "Catálogo reducido a tres apartados: %s registros archivados "
        "(%s marcas de comercios conservadas para si vuelven)",
        archived,
        marks,
    )
    if missing:
        _logger.warning(
            "Estos identificadores no existen y no se archivó nada con ellos: %s",
            ", ".join(missing),
        )

    # ------------------------------------------------------------- switch on
    # "habilita el tema por favor" (2026-08-17). Safe on every shop at once:
    # the block renders `t-if="facility_groups"`, so a shop that has ticked
    # nothing still shows nothing. What this buys is that the day a merchant
    # ticks something, it appears -- instead of appearing to do nothing.
    shops = env["res.company"].search(
        [("website_id", "!=", False), ("facility_block_enabled", "=", False)]
    )
    if shops:
        shops.write({"facility_block_enabled": True})
        _logger.info("Bloque de instalaciones activado en %s comercios", len(shops))
