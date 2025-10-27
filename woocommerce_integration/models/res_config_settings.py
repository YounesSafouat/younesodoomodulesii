from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    woocommerce_default_connection = fields.Many2one(
        'woocommerce.connection',
        string='Default WooCommerce Connection',
        config_parameter='woocommerce_integration.default_connection_id',
        help='Default WooCommerce connection for new products'
    )
