# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Untangle the Lugares de Interes taxonomy into its two real axes.

Asked for on 2026-09-02. The places-of-interest category list mixed three
different things:

* the real place types (Playas, Miradores, Edificios historicos...);
* the Memoria Viva starter set, duplicated under places at setup time and
  never used there (0 items each) -- archived here;
* an imported machine-named taxonomy (deporte_outdoor, patrimonio,
  vida_social...) that is really "what can be done there", each category
  dragging one junk subcategory per item that merely mirrors the item's
  name -- renamed to human names, classified into the new axis, its items
  moved to the activity field, and the junk subcategories deleted.

Everything is matched by NAME within the places type, never by id, and
every destructive step re-checks its precondition, so a database where a
human already cleaned part of this up is left alone.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

PLACES = "places_of_interest"

# The Memoria Viva starter set that was duplicated under places. Archived
# only while unused (0 items), which is also what they are today.
ORPHANS = [
    "General",
    "Historia",
    "Costumbres",
    "Edificios y casas",
    "Gente",
    "Fiestas",
    "Actividades",
    "Otros",
]

# Machine name -> (axis, en_US, es_ES). The axis is data, so any of these
# calls can be revisited later from the Categories backend screen.
IMPORTED = {
    "actividades": ("activity", "Activities", "Actividades"),
    "actividades_especializadas": (
        "activity", "Specialised activities", "Actividades especializadas"),
    "deporte_aventura": ("activity", "Adventure sports", "Deporte de aventura"),
    "deporte_especializados": (
        "activity", "Specialised sports", "Deportes especializados"),
    "deporte_indoor": ("activity", "Indoor sports", "Deporte indoor"),
    "deporte_outdoor": ("activity", "Outdoor sports", "Deporte al aire libre"),
    "deporte_acuatico": ("activity", "Water sports", "Deporte acuático"),
    "eventos_culturales": ("activity", "Cultural events", "Eventos culturales"),
    "eventos_deportivos": ("activity", "Sports events", "Eventos deportivos"),
    "vida_social": ("activity", "Social life", "Vida social"),
    "lugares_curiosos": ("place", "Curious places", "Lugares curiosos"),
    "patrimonio": ("place", "Heritage", "Patrimonio"),
    "servicios": ("place", "Services", "Servicios"),
    "servicios_especializados": (
        "place", "Specialised services", "Servicios especializados"),
    "spots_naturales": ("place", "Natural spots", "Espacios naturales"),
    "espacios_abiertos": ("place", "Open spaces", "Espacios abiertos"),
    "espacios_infantiles": ("place", "Children's areas", "Espacios infantiles"),
}

# Imported categories that duplicate an existing, properly named place
# type: their items move there and the machine-named copy is archived.
MERGE_INTO_PLACE = {
    "miradores": "Miradores",
    "parques": "Parques",
}


def _drop_subcategories(env, item_model, categories):
    """Unlink a category set's subcategories, clearing every pointer first.

    The UI ties an item's subcategory to its category, but this is a
    migration: it trusts nothing about how the data got here.
    """
    subcategories = categories.subcategory_ids
    if not subcategories:
        return
    item_model.search([("subcategory_id", "in", subcategories.ids)]).write(
        {"subcategory_id": False}
    )
    subcategories.unlink()


def _by_name(env, place_type, name):
    return env["website.local.content.category"].search(
        [("type_id", "=", place_type.id), ("name", "=", name)]
    )


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    place_type = env["website.local.content.type"].search([("code", "=", PLACES)])
    if not place_type:
        _logger.info("local_content: no places type, nothing to untangle.")
        return
    Item = env["website.local.content.item"].with_context(active_test=False)

    # 1. Archive the Memoria Viva starter set duplicated under places.
    archived = env["website.local.content.category"].browse()
    for name in ORPHANS:
        for cat in _by_name(env, place_type, name):
            if Item.search_count([("category_id", "=", cat.id)]):
                continue  # somebody started using it; not ours to hide
            cat.active = False
            archived |= cat

    # 2. Merge machine-named duplicates of real place types.
    for machine, human in MERGE_INTO_PLACE.items():
        source = _by_name(env, place_type, machine)
        target = _by_name(env, place_type, human).filtered("active")[:1]
        if not source or not target:
            continue
        items = Item.search([("category_id", "in", source.ids)])
        # The junk subcategory goes in the SAME write: the taxonomy
        # consistency constraint (rightly) rejects a new category with the
        # old category's subcategory still attached.
        items.write({"subcategory_id": False, "category_id": target.id})
        # Their junk subcategories die with them.
        _drop_subcategories(env, Item, source)
        source.active = False
        _logger.info(
            "local_content: %s item(s) of '%s' merged into '%s'.",
            len(items), machine, human,
        )

    # 3. The two actividades_especializadas are one category.
    twins = _by_name(env, place_type, "actividades_especializadas")
    if len(twins) > 1:
        keeper, rest = twins[0], twins[1:]
        Item.search([("category_id", "in", rest.ids)]).write(
            {"subcategory_id": False, "category_id": keeper.id}
        )
        _drop_subcategories(env, Item, rest)
        rest.active = False

    # 4. Rename, classify, and strip the machine names' junk.
    moved = 0
    for machine, (axis, name_en, name_es) in IMPORTED.items():
        for cat in _by_name(env, place_type, machine).filtered("active"):
            cat.axis = axis
            # The stale machine name may sit in every installed language:
            # rewrite the base and Spanish, and let the other languages
            # fall back to the new base until the translator refills them.
            cr.execute(
                "UPDATE website_local_content_category "
                "SET name = jsonb_build_object('en_US', %s, 'es_ES', %s) "
                "WHERE id = %s",
                (name_en, name_es, cat.id),
            )
            cat.invalidate_recordset(["name"])
            items = Item.search([("category_id", "=", cat.id)])
            if axis == "activity":
                # The place field held what was really an activity. Move
                # it; the place type stays empty until somebody fills it.
                items.write(
                    {
                        "activity_category_ids": [(4, cat.id)],
                        "category_id": False,
                        "subcategory_id": False,
                    }
                )
                moved += len(items)
            # One junk subcategory per item, mirroring the item's name.
            _drop_subcategories(env, Item, cat)

    _logger.info(
        "local_content: %s starter categories archived, %s item(s) moved "
        "to the activity axis.",
        len(archived), moved,
    )
