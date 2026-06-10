# -*- coding: utf-8 -*-
"""ZCA Platform — capa de seguridad ORM (complemento a ir.rule).

- `_search` con ormcache + scoping + context guard anti-recursión.
- Admin (group_system) bypasea ir.rules por diseño Odoo → filtro empresa vía _search.
- ZCA users: además se excluyen partners/users de administradores.
- `create` y `write` bloquean escalada de privilegios SIEMPRE (incluso self-write).
- Compat Odoo 17/18/19 vía **kw con pop de access_rights_uid.
"""
from odoo import api, models, tools, _
from odoo.exceptions import AccessError

_SYSTEM_GROUP = "base.group_system"


def _is_zca_user(user):
    return (
        user.has_group("zca_platform.group_zca_comercio_manager")
        or user.has_group("zca_platform.group_zca_comercio_basic")
    )


def _m2m_new_group_set(existing_ids, commands):
    """Aplica commands x2many. Cubre ops 0,3,4,5,6 y lista literal [ids]."""
    if isinstance(commands, (list, tuple)) and commands and all(isinstance(x, int) for x in commands):
        return set(existing_ids), set(commands)
    new = set(existing_ids)
    for cmd in commands or ():
        if not isinstance(cmd, (list, tuple)) or not cmd:
            continue
        op = cmd[0]
        if op == 3 and len(cmd) >= 2: new.discard(cmd[1])
        elif op == 4 and len(cmd) >= 2: new.add(cmd[1])
        elif op == 5: new = set()
        elif op == 6 and len(cmd) >= 3: new = set(cmd[2] or ())
    return set(existing_ids), new


class ZcaResPartnerSecurity(models.Model):
    _inherit = "res.partner"

    @api.model
    @tools.ormcache()
    def _zca_admin_partner_ids(self):
        # SQL directo + solo usuarios ACTIVOS: evita incluir __system__ (active=False)
        # que causaría AccessError al inicializar la sesión de mensajería post-login.
        self.env.cr.execute("""
            SELECT u.partner_id
              FROM res_users u
              JOIN res_groups_users_rel r ON r.uid = u.id
              JOIN ir_model_data d ON d.res_id = r.gid AND d.model = 'res.groups'
             WHERE d.module = 'base' AND d.name = 'group_system'
               AND u.partner_id IS NOT NULL
               AND u.active = TRUE
        """)
        return tuple(row[0] for row in self.env.cr.fetchall())

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, **kw):
        kw.pop("access_rights_uid", None)
        if self.env.context.get("_zca_partner_guard") or self.env.su:
            return super()._search(domain, offset=offset, limit=limit, order=order, **kw)

        user = self.env.user
        # Fijar guard ANTES de cualquier acceso ORM para evitar recursión
        self = self.with_context(_zca_partner_guard=True)

        # Usar la empresa ACTIVA de la sesión (no la empresa principal del usuario).
        # env.company.id refleja el contexto real del usuario (cookie cids),
        # mientras que user.company_id.id es siempre la empresa principal,
        # lo que puede diferir cuando el usuario ha cambiado de empresa.
        active_co = self.env.company.id
        is_admin = user.has_group(_SYSTEM_GROUP)

        if is_admin or _is_zca_user(user):
            if active_co:
                # Filtro empresa: company_id=False incluido para ambos
                # (OdooBot/Administrator tienen company_id=NULL y son necesarios)
                # Los partners de usuarios básicos ya tienen company_id asignado
                # via SQL en hooks.py, así que company_id=False no filtra basura
                domain = (
                    ['|', ('company_id', '=', active_co), ('company_id', '=', False)]
                    + list(domain)
                )
                if not is_admin:
                    # ZCA users: excluir además partners de administradores activos
                    admin_ids = self._zca_admin_partner_ids()
                    if admin_ids:
                        domain = [("id", "not in", list(admin_ids))] + list(domain)

        return super()._search(domain, offset=offset, limit=limit, order=order, **kw)


class ZcaResUsersSecurity(models.Model):
    _inherit = "res.users"

    @api.model
    @tools.ormcache()
    def _zca_admin_user_ids(self):
        # SQL directo + solo usuarios ACTIVOS: excluye __system__ (active=False)
        self.env.cr.execute("""
            SELECT r.uid
              FROM res_groups_users_rel r
              JOIN ir_model_data d ON d.res_id = r.gid AND d.model = 'res.groups'
              JOIN res_users u ON u.id = r.uid
             WHERE d.module = 'base' AND d.name = 'group_system'
               AND u.active = TRUE
        """)
        return tuple(row[0] for row in self.env.cr.fetchall())

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, **kw):
        kw.pop("access_rights_uid", None)
        if self.env.context.get("_zca_users_guard") or self.env.su:
            return super()._search(domain, offset=offset, limit=limit, order=order, **kw)
        user = self.env.user
        if _is_zca_user(user) and not user.has_group(_SYSTEM_GROUP):
            self = self.with_context(_zca_users_guard=True)  # guarda ANTES del ormcache
            active_co = self.env.company.id
            # Filtro por empresa activa: solo usuarios cuya empresa principal coincide
            # O el propio usuario (para que pueda verse a sí mismo)
            if active_co:
                domain = (
                    ['|', ('id', '=', user.id), ('company_id', '=', active_co)]
                    + list(domain)
                )
            # Excluir administradores activos
            admin_ids = self._zca_admin_user_ids()
            if admin_ids:
                domain = [("id", "not in", list(admin_ids))] + list(domain)
        return super()._search(domain, offset=offset, limit=limit, order=order, **kw)

    # ─── Anti-escalada (SIEMPRE, incluso self-write) ───
    def _zca_check_group_escalation(self, vals, existing_ids=()):
        if self.env.su or self.env.user.has_group(_SYSTEM_GROUP):
            return
        if not _is_zca_user(self.env.user):
            return
        commands = vals.get("groups_id") or vals.get("group_ids")
        if commands is None:
            return
        basic = self.env.ref("zca_platform.group_zca_comercio_basic", raise_if_not_found=False)
        if not basic:
            return
        allowed = set((basic | basic.trans_implied_ids).ids)
        _, new = _m2m_new_group_set(existing_ids, commands)
        added = new - set(existing_ids)
        forbidden = added - allowed
        if forbidden:
            names = ", ".join(self.env["res.groups"].sudo().browse(list(forbidden)).mapped("name"))
            raise AccessError(_(
                "Un Gestor ZCA solo puede asignar el grupo 'Usuario Básico ZCA'. "
                "Grupos no permitidos: %s"
            ) % names)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._zca_check_group_escalation(vals, existing_ids=())
        return super().create(vals_list)

    def write(self, vals):
        for user in self:
            existing = getattr(user, "group_ids", None) or getattr(user, "groups_id", None)
            existing_ids = existing.ids if existing is not None else ()
            self._zca_check_group_escalation(vals, existing_ids=existing_ids)
        return super().write(vals)
