# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""
LOGIN - Versión Core Odoo
=========================

Fix realizado (2026-04-01):
- Eliminado método _login_redirect que causaba bucles de redirección
- El core de Odoo (web.controllers.home.Home) maneja la redirección correctamente:
  * Establece cookie cids con la compañía del website
  * Verifica si el usuario es interno (is_user_internal)
  * Redirige internos a /odoo y externos a /web/login_successful

Documentación: docs/core_modifications/2026-04-01_fix_redireccion_login/
"""

from odoo import http
from odoo.addons.web.controllers.home import Home


class LoginCompanyController(Home):
    """
    Controlador de login - Ahora delega al core de Odoo.
    
    El método _login_redirect del core maneja:
    - Establecimiento de cookie cids para el microsite
    - Redirección según tipo de usuario (interno/externo)
    - Evita bucles de redirección
    """
    pass
