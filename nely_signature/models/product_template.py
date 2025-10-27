from odoo import models, fields, api, _

import logging

_logger = logging.getLogger(__name__)

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    kwh = fields.Float(
        string='KWh',
        default=380000,
    )
    prime_product = fields.Boolean(
        string='Prime Product',
        default=False,
        help="Indicates if this product is eligible for a prime incentive.",
    )

   
class ProductProduct(models.Model):
    _inherit = 'product.product'

    kwh = fields.Float(
        string='KWh',
        related='product_tmpl_id.kwh',
        store=True,
    )
    prime_product = fields.Boolean(
        string='Prime Product',

        related='product_tmpl_id.prime_product', store=True,
    )
   