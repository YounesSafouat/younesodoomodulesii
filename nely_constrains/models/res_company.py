from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class ResCompany(models.Model):
    _inherit = 'res.company'

    elligible_ape_ids = fields.One2many('res.ape.elligible', 'company_id', string='Eligible APE')


    def is_elligible_ape(self, ape_code):
        self.ensure_one()
        if not self.elligible_ape_ids:
            return True, 1
        if not ape_code:
            return False, 0.0
        for ape in self.elligible_ape_ids:
            if ape.ape == ape_code:
                return True, ape.coefficient
        return False, 0.0

class ResCompanyElligible(models.Model):
    _name = 'res.ape.elligible'
    _description = 'Eligible Company'

    company_id = fields.Many2one('res.company', string='Company', required=True, ondelete='cascade')
    ape = fields.Char( string='Code APE', required=True)
    coefficient = fields.Float(string='Coefficient', required=True, default=1.0)