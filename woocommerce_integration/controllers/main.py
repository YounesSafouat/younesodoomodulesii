from odoo import http
from odoo.http import request


class WooCommerceController(http.Controller):
    
    @http.route('/woocommerce/webhook', type='json', auth='public', csrf=False)
    def webhook(self, **kwargs):
        """Handle WooCommerce webhooks"""
        return {'status': 'success'}
