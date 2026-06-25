# -*- coding: utf-8 -*-
"""Limpia los registros de seguridad HUÉRFANOS de versiones anteriores.

Versiones previas del módulo dejaron una categoría, un privilegio y un grupo
"Aprobador" llamados "Memoria Viva" SIN xmlid (no los gestiona ya ningún
``ir.model.data``). Eso hacía que en el formulario de usuario apareciera una
SEGUNDA caja "Memoria Viva" duplicada y vacía. Aquí se eliminan de forma segura
(vía ORM, que arrastra membresías e implicaciones).

Tras cargar el nuevo ``security/memoria_viva_security.xml`` (que renombra el
privilegio canónico a "Historias"), el único privilegio que queda llamado
"Memoria Viva" es el huérfano, así que el criterio "nombre 'Memoria Viva' sin
xmlid" lo identifica sin riesgo de tocar los registros canónicos.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def _has_xmlid(env, model, res_id):
    return bool(
        env["ir.model.data"]
        .sudo()
        .search_count([("model", "=", model), ("res_id", "=", res_id)])
    )


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})

    privileges = (
        env["res.groups.privilege"].sudo().search([("name", "=", "Memoria Viva")])
    )
    orphan_privs = privileges.filtered(
        lambda p: not _has_xmlid(env, "res.groups.privilege", p.id)
    )

    borrados = {"privilegios": 0, "grupos": 0, "categorias": 0}
    for priv in orphan_privs:
        categoria = priv.category_id
        grupos = env["res.groups"].sudo().search([("privilege_id", "=", priv.id)])
        orphan_groups = grupos.filtered(
            lambda g: not _has_xmlid(env, "res.groups", g.id)
        )
        borrados["grupos"] += len(orphan_groups)
        orphan_groups.unlink()
        priv.unlink()
        borrados["privilegios"] += 1

        cat_aun_usada = (
            env["res.groups.privilege"]
            .sudo()
            .search_count([("category_id", "=", categoria.id)])
            if categoria
            else 0
        )
        if (
            categoria
            and not _has_xmlid(env, "ir.module.category", categoria.id)
            and not cat_aun_usada
        ):
            categoria.unlink()
            borrados["categorias"] += 1

    _logger.info(
        "memoria_viva: limpieza de seguridad huérfana -> %s privilegio(s), "
        "%s grupo(s), %s categoría(s) eliminados.",
        borrados["privilegios"],
        borrados["grupos"],
        borrados["categorias"],
    )
