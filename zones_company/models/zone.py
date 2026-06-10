from odoo import models, fields, api

class Zone(models.Model):
    _name = 'zone'
    _description = 'Zona'
    _order = 'sequence, name'
    _rec_name = 'name'

    name = fields.Char(string='Nombre', required=True, translate=True)
    code = fields.Char(string='Código', required=True)
    description = fields.Text(string='Descripción', translate=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True, 
        help='Si se desmarca, la zona se archiva y no aparece en búsquedas.')
    company_ids = fields.One2many('res.company', 'zone_id', string='Empresas')
    company_count = fields.Integer(
        string='Nº de Empresas',
        compute='_compute_company_count',
        store=True
    )

    # Constraint de Odoo 19
    _unique_code = models.Constraint(
        'unique(code)',
        '¡El código de la zona debe ser único!'
    )

    @api.depends('company_ids')
    def _compute_company_count(self):
        for zone in self:
            zone.company_count = len(zone.company_ids)

    def unlink(self):
        """
        Override unlink to also remove ir.model.data references.
        This prevents deleted zones from being recreated on module update.
        """
        if self.ids:
            self.env['ir.model.data'].sudo().search([
                ('model', '=', self._name),
                ('res_id', 'in', self.ids)
            ]).unlink()
        return super().unlink()
