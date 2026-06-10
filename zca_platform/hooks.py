# -*- coding: utf-8 -*-
"""ZCA Platform — hooks de instalación y migración.

post_init  → primera instalación.
post_migrate → upgrade (llamado desde migrations/19.0.x.x/post-migration.py).

NO se toca base.res_partner_rule: el dominio estándar de Odoo 19
('partner_share', 'company_id parent_of', etc.) es compatible con nuestra
capa de seguridad (_search override + ir.rules por grupo).
"""
import logging
_logger = logging.getLogger(__name__)


def _apply_zca_fixes(cr):
    """Fixes de BD idempotentes. Corre tanto en install como en upgrade.

    1. OdooBot (partner id=2) sin empresa — es un partner técnico del sistema,
       no pertenece a ninguna empresa real. Queda fuera de todos los filtros
       por company_id y es inactivo, así que no aparece en búsquedas normales.

    2. Partner de cada res.company recibe company_id = esa empresa.
       Necesario para que los Gestores puedan ver el propio partner de su empresa.

    3. Partners de usuarios (Gestores, Básicos, Admins) reciben company_id
       del usuario al que están vinculados. Evita que aparezcan cross-company
       via el branch company_id=False del _search override.
       Excepción: OdooBot (id=2) se mantiene sin empresa (paso 1).

    4. Parámetros de sistema: desactiva catálogo y usuarios compartidos.
    """
    _logger.info("ZCA: aplicando fixes de BD")

    # 1. OdooBot sin empresa
    cr.execute("""
        UPDATE res_partner
           SET company_id = NULL, write_date = NOW()
         WHERE id = 2 AND company_id IS NOT NULL
    """)

    # 2. Partners de empresas anclados a su empresa
    cr.execute("""
        UPDATE res_partner rp
           SET company_id = rc.id, write_date = NOW()
          FROM res_company rc
         WHERE rc.partner_id = rp.id
           AND (rp.company_id IS NULL OR rp.company_id <> rc.id)
    """)

    # 3. Partners de usuarios sin company_id asignado
    cr.execute("""
        UPDATE res_partner rp
           SET company_id = u.company_id, write_date = NOW()
          FROM res_users u
         WHERE u.partner_id = rp.id
           AND u.company_id IS NOT NULL
           AND rp.company_id IS NULL
           AND rp.id <> 2
    """)

    # 4. Parámetros de sistema
    cr.execute("""
        INSERT INTO ir_config_parameter
               (key, value, create_uid, write_uid, create_date, write_date)
        VALUES ('res.partner.share',       'False', 1, 1, NOW(), NOW()),
               ('base_setup.default_user', 'False', 1, 1, NOW(), NOW())
        ON CONFLICT (key) DO UPDATE
           SET value = EXCLUDED.value, write_uid = 1, write_date = NOW()
    """)

    # 5. Propagación de grupos implicados para usuarios creados vía SQL.
    #    Odoo propaga implied_ids solo cuando el grupo se asigna por ORM/UI.
    #    Usuarios admin creados directamente en BD pueden quedar sin group_erp_manager,
    #    lo que les impide ver empresas (res.company está cubierto por esa regla).
    #    Aquí forzamos: todo usuario con group_system recibe también group_erp_manager.
    cr.execute("""
        INSERT INTO res_groups_users_rel (gid, uid)
        SELECT gg.id AS gid, gu.uid
          FROM res_groups_users_rel gu
          JOIN res_groups gs ON gs.id = gu.gid
          JOIN ir_model_data imd_sys
               ON imd_sys.res_id = gs.id
              AND imd_sys.model = 'res.groups'
              AND imd_sys.module = 'base'
              AND imd_sys.name = 'group_system'
          JOIN ir_model_data imd_erp
               ON imd_erp.model = 'res.groups'
              AND imd_erp.module = 'base'
              AND imd_erp.name = 'group_erp_manager'
          JOIN res_groups gg ON gg.id = imd_erp.res_id
         WHERE NOT EXISTS (
               SELECT 1 FROM res_groups_users_rel x
                WHERE x.gid = gg.id AND x.uid = gu.uid
         )
        ON CONFLICT DO NOTHING
    """)

    # 6. Limpiar menús con action huérfana (apuntan a act_window que ya no existe).
    #    Solo pone action=NULL — no elimina el menú ni sus hijos.
    cr.execute("""
        UPDATE ir_ui_menu
           SET action = NULL
         WHERE action LIKE 'ir.actions.act_window,%%'
           AND CAST(split_part(action, ',', 2) AS INTEGER)
               NOT IN (SELECT id FROM ir_act_window)
    """)

    # 7. Reasignar menú 'Contacts' (module=contacts, name=menu_contacts)
    #    si su action quedó NULL por el paso anterior.
    cr.execute("""
        UPDATE ir_ui_menu m
           SET action = 'ir.actions.act_window,' || aw.id::text
          FROM ir_model_data mm
          JOIN ir_model_data ad
               ON ad.model  = 'ir.actions.act_window'
              AND ad.module = 'contacts'
              AND ad.name   = 'action_contacts'
          JOIN ir_act_window aw ON aw.id = ad.res_id
         WHERE mm.model  = 'ir.ui.menu'
           AND mm.module = 'contacts'
           AND mm.name   = 'menu_contacts'
           AND mm.res_id = m.id
           AND (m.action IS NULL OR m.action = '')
    """)

    # 8. Limpiar action_id huérfano en res_users
    #    (acción de inicio que apunta a un act_window eliminado → pantalla en blanco).
    cr.execute("""
        UPDATE res_users
           SET action_id = NULL
         WHERE action_id IS NOT NULL
           AND action_id NOT IN (
               SELECT id FROM ir_act_window
               UNION ALL
               SELECT id FROM ir_act_url
               UNION ALL
               SELECT id FROM ir_act_client
           )
    """)

    # 9. Eliminar regla ir.rule global 'rule_partner_global_by_company' si existe.
    #    Fue añadida en una versión anterior y luego eliminada del XML. Con noupdate=0
    #    Odoo no elimina automáticamente registros quitados del XML, así que lo
    #    hacemos aquí de forma idempotente.
    cr.execute("""
        DELETE FROM ir_rule
         WHERE id IN (
             SELECT r.id
               FROM ir_rule r
               JOIN ir_model_data imd
                    ON imd.res_id = r.id
                   AND imd.model  = 'ir.rule'
                   AND imd.module = 'zca_platform'
                   AND imd.name   = 'rule_partner_global_by_company'
         )
    """)

    _logger.info("ZCA: fixes de BD completados")


def _extract_cr(*args):
    """Compat defensiva entre firmas de Odoo (env vs (cr, registry))."""
    if len(args) == 1 and hasattr(args[0], "cr"):
        return args[0].cr
    if len(args) >= 1:
        return args[0]
    raise TypeError("ZCA hooks: no se pudo extraer cursor del argumento")


def post_init(*args):
    """Corre una sola vez al instalar el módulo por primera vez."""
    cr = _extract_cr(*args)
    _logger.info("ZCA: post_init iniciado")
    _apply_zca_fixes(cr)
    _logger.info("ZCA: post_init completado")


def post_migrate(*args):
    """Corre en cada upgrade. Llamado desde migrations/<ver>/post-migration.py."""
    cr = _extract_cr(*args)
    _logger.info("ZCA: post_migrate iniciado")
    _apply_zca_fixes(cr)
    _logger.info("ZCA: post_migrate completado")
