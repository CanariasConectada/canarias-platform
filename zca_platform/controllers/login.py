# -*- coding: utf-8 -*-
"""ZCA Platform — Override seguro de _login_redirect.

El core de Odoo en canariasconectada.es tiene un parche directo en
addons/web/controllers/home.py que busca el website por host y forza
la empresa del website en la cookie 'cids'.

Problema: si el usuario NO tiene acceso a la empresa del website,
el parche no establece 'cids' → el frontend detecta mismatch de empresa
y redirige a login repetidamente (login bounce).

Esta clase hereda Home y sobreescribe _login_redirect con lógica robusta:
- Si website.company_id ∈ user.company_ids → comportamiento estándar del parche
- Si NO → usa user.company_id como fallback (sin bounce)
- Si no hay website para el host → usa user.company_id directamente
"""
import logging

from odoo import http
from odoo.addons.web.controllers.home import Home

_logger = logging.getLogger(__name__)


class ZcaLoginController(Home):

    def _login_redirect(self, uid, redirect=None):
        """Login redirect con fallback seguro de empresa."""
        try:
            request = http.request
            env = request.env

            # Buscar website por host (igual que el parche del core)
            host = request.httprequest.host
            website = env['website'].sudo().search(
                [('domain', 'ilike', host)], limit=1
            )

            if website and website.company_id:
                user = env['res.users'].sudo().browse(uid)
                user_company_ids = user.company_ids.ids

                if website.company_id.id in user_company_ids:
                    # Usuario tiene acceso a la empresa del website → usar esa
                    target_company_id = website.company_id.id
                    _logger.info(
                        "ZCA login_redirect: user=%s website_company=%s (ok)",
                        uid, target_company_id
                    )
                else:
                    # Sin acceso a la empresa del website → fallback a empresa principal
                    target_company_id = user.company_id.id
                    _logger.info(
                        "ZCA login_redirect: user=%s website_company=%s NO en company_ids=%s "
                        "→ fallback a company=%s",
                        uid, website.company_id.id, user_company_ids, target_company_id
                    )

                # Establecer cookie cids para evitar mismatch en el frontend
                cids_value = str(target_company_id)
                # La respuesta futura puede no estar disponible en todos los contextos;
                # usamos set_cookie con try/except defensivo
                try:
                    request.future_response.set_cookie(
                        'cids', cids_value, max_age=31536000, httponly=False
                    )
                except Exception:
                    pass  # fuera de contexto HTTP completo — no crítico

        except Exception as exc:
            # Nunca fallar aquí; si algo va mal, dejamos al padre manejar el redirect
            _logger.warning("ZCA login_redirect: error en lógica ZCA: %s", exc)

        return super()._login_redirect(uid, redirect=redirect)
