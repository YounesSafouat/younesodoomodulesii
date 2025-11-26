from odoo.tests.common import HttpCase
from odoo import http
from unittest.mock import patch, MagicMock
import json


class TestWooCommerceWebhook(HttpCase):

    def setUp(self):
        super(TestWooCommerceWebhook, self).setUp()
        self.connection = self.env['woocommerce.connection'].create({
            'name': 'Test Store',
            'store_url': 'https://teststore.com',
            'consumer_key': 'test_key',
            'consumer_secret': 'test_secret',
            'api_version': 'v3',
        })
        
        self.webhook = self.env['woocommerce.order.webhook'].create({
            'name': 'Test Webhook',
            'connection_id': self.connection.id,
            'webhook_topic': 'order.created',
            'active': True,
            'auto_create_odoo_order': True,
            'auto_create_customer': True,
        })

    def test_webhook_get_request(self):
        url = f'/woocommerce/webhook/{self.webhook.id}'
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')

    def test_webhook_inactive(self):
        self.webhook.active = False
        self.webhook.flush_recordset()
        
        url = f'/woocommerce/webhook/{self.webhook.id}'
        response = self.url_open(url)
        self.assertEqual(response.status_code, 404)

    def test_webhook_not_found(self):
        url = '/woocommerce/webhook/99999'
        response = self.url_open(url)
        self.assertEqual(response.status_code, 404)

    @patch('odoo.addons.woocommerce_integration.models.woocommerce_order_webhook.WooCommerceOrderWebhook.process_webhook_data')
    def test_webhook_post_request(self, mock_process):
        mock_order = MagicMock()
        mock_order.name = 'SO001'
        mock_process.return_value = mock_order
        
        order_data = {
            'id': 123,
            'status': 'processing',
            'billing': {
                'first_name': 'John',
                'last_name': 'Doe',
                'email': 'john@example.com'
            },
            'line_items': []
        }
        
        url = f'/woocommerce/webhook/{self.webhook.id}'
        headers = {'Content-Type': 'application/json'}
        response = self.url_open(
            url,
            data=json.dumps(order_data).encode(),
            headers=headers
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')

    def test_webhook_invalid_json(self):
        url = f'/woocommerce/webhook/{self.webhook.id}'
        headers = {'Content-Type': 'application/json'}
        response = self.url_open(
            url,
            data='invalid json'.encode(),
            headers=headers
        )
        
        self.assertEqual(response.status_code, 400)

    def test_webhook_test_endpoint(self):
        url = f'/woocommerce/webhook/test/{self.webhook.id}'
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('active and ready', response.text)

    def test_verify_webhook_signature(self):
        from unittest.mock import Mock
        
        from odoo.addons.woocommerce_integration.controllers import webhook_controller
        
        secret = 'test_secret'
        body = b'test body'
        
        mock_request = Mock()
        mock_request.headers = {}
        mock_request.get_data.return_value = body
        
        controller = webhook_controller.WooCommerceWebhookController()
        result = controller._verify_webhook_signature(mock_request, secret)
        self.assertFalse(result)

