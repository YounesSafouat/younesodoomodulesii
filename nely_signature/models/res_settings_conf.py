from odoo import models, fields, api, _

import logging

_logger = logging.getLogger(__name__)

class ResSettingsConf(models.TransientModel):
    _inherit = 'res.config.settings'

    sale_product_id = fields.Many2one(
        'product.product',
        related='company_id.signature_product_id', readonly=False, domain="[('sale_ok', '=', True)]",
        string='Sale Product',
    )
    prime_product_id = fields.Many2one(
        'product.product',
        related='company_id.prime_product_id', domain="[('prime_product', '=', True)]", readonly=False,
        string='Prime Product',
    )


class ResCompany(models.Model):
    _inherit = 'res.company'

    signature_product_id = fields.Many2one(
        'product.product',
        string='Signature Product', ondelete="restrict"
    )
    prime_product_id = fields.Many2one(
        'product.product',
        string='Prime Product', ondelete="restrict"
    )

