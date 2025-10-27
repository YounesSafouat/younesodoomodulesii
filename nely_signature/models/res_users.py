from odoo import models, fields, api, _

class ResUser(models.Model):
    _inherit = 'res.users'

    sale_representative_id = fields.Many2one(
        'res.partner',
        string='Sale Representative',
        help="Sale representative for this user", ondelete="restrict",
    )