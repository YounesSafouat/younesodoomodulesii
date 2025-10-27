from odoo import models, fields, api

class PappersFieldMapping(models.Model):
    _name = 'pappers.field.mapping'
    _description = 'Pappers Field Mapping'
    _rec_name = 'odoo_field'

    odoo_field = fields.Char(string='Odoo Field', required=True,
        help="Technical name of the Odoo field (e.g. 'name', 'slistt', 'siret_pappers')")
    pappers_field = fields.Char(string='Pappers Field', required=True,
        help="Technical name of the Pappers field (e.g. 'siren', 'siege.code_postal')")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)

    _sql_constraints = [
        ('unique_field_mapping', 'unique(pappers_field,company_id)', 'A mapping already exists for this Pappers field!')
    ]

    @api.model_create_multi
    def create(self, vals):
        """Override create to ensure odoo_field exists in res.partner"""
        for val in vals:
            if val.get('odoo_field'):
                if not self.env['res.partner']._fields.get(val['odoo_field']):
                    raise ValueError(f"Field {val['odoo_field']} does not exist in res.partner model")
        return super().create(vals)

    def write(self, vals):
        """Override write to ensure odoo_field exists in res.partner"""
        if vals.get('odoo_field'):
            if not self.env['res.partner']._fields.get(vals['odoo_field']):
                raise ValueError(f"Field {vals['odoo_field']} does not exist in res.partner model")
        return super().write(vals)