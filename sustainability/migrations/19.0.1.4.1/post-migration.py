# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Backfill al gatear el menú/acceso de Sostenibilidad por grupo específico.

Antes, Sostenibilidad colgaba de ``base.group_user`` (todos los internos). Ahora
la visibilidad y el acceso dependen de ``group_sustainability_user``, asignable
por usuario. Para no quitarle la capacidad de evaluar a quien ya la tenía, aquí
asignamos ``group_sustainability_user`` a todos los usuarios internos activos
existentes. Los usuarios nuevos quedan en "No" por defecto.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    group = env.ref("sustainability.group_sustainability_user")
    internal_users = env["res.users"].search(
        [("share", "=", False), ("active", "=", True)]
    )
    group.sudo().write({"user_ids": [(4, user.id) for user in internal_users]})
    _logger.info(
        "sustainability: group_sustainability_user asignado a %s usuarios "
        "internos activos.",
        len(internal_users),
    )

    # El menú raíz quedó ligado a base.group_user en instalaciones <=1.3.0. El
    # atributo `groups` del menuitem solo AÑADE grupos (Command.link), nunca los
    # quita, así que aquí desvinculamos base.group_user para que la visibilidad
    # dependa solo de group_sustainability_user.
    menu = env.ref("sustainability.menu_sustainability_root")
    menu.sudo().write({"group_ids": [(3, env.ref("base.group_user").id)]})
