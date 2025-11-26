import logging
from odoo import http

_logger = logging.getLogger(__name__)

class TestController(http.Controller):
    
    @http.route('/test/webhook', type='http', auth='public', methods=['GET'], csrf=False)
    def test_webhook(self, **kwargs):
        _logger.info("TEST: /test/webhook called!")
        return http.Response('Webhook test endpoint is working!')
