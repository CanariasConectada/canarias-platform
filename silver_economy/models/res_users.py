# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, _
from odoo.exceptions import UserError


class ResUsers(models.Model):
    _inherit = 'res.users'

    def action_open_silver_evaluations(self):
        """Acción para abrir el listado de evaluaciones Silver Economy del usuario"""
        self.ensure_one()
        return {
            'name': _('Mis evaluaciones Silver Economy'),
            'type': 'ir.actions.act_window',
            'res_model': 'survey.user_input',
            'view_mode': 'list,form',
            'domain': [
                ('survey_id.is_silver_economy', '=', True),
                ('company_id', 'in', self.company_ids.ids),
                ('test_entry', '=', False),
            ],
            'context': {'create': False},
        }
