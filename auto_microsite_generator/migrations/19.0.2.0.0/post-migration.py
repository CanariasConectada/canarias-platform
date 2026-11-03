# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Heal the directory menu of microsites created before the labels were seeded.

Website 221 shipped with a directory entry reading Trade / Handel / Commerce
/ Commercio, because "Comercio" was left to the machine translator, which has
no way to know it is the name of the directory rather than the noun. The 206
migrated sites were corrected by hand at the time; this repairs whatever was
created after them, and is a no-op on the ones already right.

Deliberately narrow, in two ways:

* only ``/comercio`` is touched. Home and Shop translate cleanly and were
  never the complaint, so there is nothing to gain by rewriting them and a
  merchant's rename to lose;
* the raw jsonb is read rather than the field. Reading a translatable field
  in a language it has no key for silently returns the ``en_US`` base, which
  is indistinguishable from a real translation -- and would make every
  untranslated language look like somebody's decision. A language is only
  written when it holds nothing of its own, or holds one of the renderings
  we know a machine produced.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

DIRECTORY_URL = "/comercio"

# A copy of ``MENU_LABELS['/comercio']`` rather than an import of it: Odoo
# loads a migration script standalone, outside the addon package, so a
# relative import fails at load time. Copying is also the honest thing for a
# migration -- it must keep doing what it did on the day it ran, even if the
# module's wording changes later.
DIRECTORY_LABELS = {
    "es_ES": "Comercio",
    "en_US": "Directory",
    "de_DE": "Verzeichnis",
    "fr_FR": "Annuaire",
    "it_IT": "Elenco",
    "pl_PL": "Katalog",
    "pt_PT": "Diretório",
}

# Every value the estate actually holds for this menu other than the estate
# wording, measured across the 211 live websites, plus the untranslated
# Spanish source. Nothing is replaced on a guess.
MACHINE_RENDERINGS = {
    "Trade",  # en_US
    "Handel",  # de_DE and pl_PL
    "Commerce",  # fr_FR
    "Commercio",  # it_IT
    "Comércio",  # pt_PT
    "Comercio",  # the source string, left behind untranslated
}


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    installed = {lang[0] for lang in env["res.lang"].get_installed()}
    labels = {
        lang: label for lang, label in DIRECTORY_LABELS.items() if lang in installed
    }
    if not labels:
        return

    cr.execute(
        "SELECT id, name FROM website_menu "
        "WHERE url = %s AND website_id IS NOT NULL",
        (DIRECTORY_URL,),
    )
    rows = cr.fetchall()

    Menu = env["website.menu"]
    healed = 0
    for menu_id, stored in rows:
        stored = stored if isinstance(stored, dict) else {}
        for lang, label in labels.items():
            held = stored.get(lang)
            if held == label:
                continue
            if held and held not in MACHINE_RENDERINGS:
                # A rename, or a correction somebody typed. Not ours.
                continue
            Menu.browse(menu_id).with_context(lang=lang).name = label
            healed += 1
    _logger.info(
        "Directory menu wording healed on %s menu/language pairs across %s menus.",
        healed,
        len(rows),
    )
