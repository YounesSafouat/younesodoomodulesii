from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError
from unittest.mock import patch, MagicMock
import json


class TestWooCommerceProduct(TransactionCase):

    def setUp(self):
        super(TestWooCommerceProduct, self).setUp()
        self.connection = self.env['woocommerce.connection'].create({
            'name': 'Test Store',
            'store_url': 'https://teststore.com',
            'consumer_key': 'test_key',
            'consumer_secret': 'test_secret',
            'api_version': 'v3',
        })
        
        self.wc_product = self.env['woocommerce.product'].create({
            'name': 'Test Product',
            'wc_product_id': 123,
            'connection_id': self.connection.id,
            'price': 29.99,
            'regular_price': 29.99,
            'status': 'publish',
        })

    def test_product_creation(self):
        self.assertEqual(self.wc_product.name, 'Test Product')
        self.assertEqual(self.wc_product.wc_product_id, 123)
        self.assertEqual(self.wc_product.connection_id.id, self.connection.id)

    def test_compute_wc_data_formatted(self):
        test_data = {'id': 123, 'name': 'Test Product'}
        self.wc_product.wc_data = json.dumps(test_data)
        self.wc_product._compute_wc_data_formatted()
        self.assertIn('Test Product', self.wc_product.wc_data_formatted)

    def test_compute_is_variable_product(self):
        variable_data = {'type': 'variable', 'name': 'Variable Product'}
        self.wc_product.wc_data = json.dumps(variable_data)
        self.wc_product._compute_is_variable_product()
        self.assertTrue(self.wc_product.is_variable_product)
        
        simple_data = {'type': 'simple', 'name': 'Simple Product'}
        self.wc_product.wc_data = json.dumps(simple_data)
        self.wc_product._compute_is_variable_product()
        self.assertFalse(self.wc_product.is_variable_product)

    def test_compute_image_count(self):
        self.assertEqual(self.wc_product.image_count, 0)
        
        self.env['woocommerce.product.image'].create({
            'name': 'Image 1',
            'product_id': self.wc_product.id,
        })
        self.wc_product._compute_image_count()
        self.assertEqual(self.wc_product.image_count, 1)

    def test_compute_variant_count(self):
        self.assertEqual(self.wc_product.variant_count, 0)

    @patch('odoo.addons.woocommerce_integration.models.woocommerce_connection.requests.put')
    @patch('odoo.addons.woocommerce_integration.models.woocommerce_connection.requests.get')
    def test_write_syncs_to_woocommerce(self, mock_get, mock_put):
        # Mock the GET request for fetching current product data
        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            'id': 123,
            'name': 'Test Product',
            'regular_price': '29.99',
            'status': 'publish',
            'attributes': []
        }
        mock_get_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_get_response
        
        # Mock the PUT request for updating product
        mock_put_response = MagicMock()
        mock_put_response.status_code = 200
        mock_put_response.json.return_value = {
            'id': 123,
            'name': 'Updated Product',
            'regular_price': '39.99'
        }
        mock_put_response.raise_for_status = MagicMock()
        mock_put.return_value = mock_put_response
        
        self.wc_product.write({
            'name': 'Updated Product',
            'regular_price': 39.99
        })
        self.assertEqual(self.wc_product.name, 'Updated Product')
        self.assertEqual(self.wc_product.regular_price, 39.99)
        
        # Verify that the HTTP requests were called
        self.assertTrue(mock_put.called, "PUT request should be called to update product")

    def test_create_from_wc_data(self):
        wc_data = {
            'id': 456,
            'name': 'New Product',
            'sku': 'SKU-123',
            'price': '19.99',
            'regular_price': '19.99',
            'sale_price': '',
            'stock_status': 'instock',
            'status': 'publish',
            'featured': False,
            'categories': [],
            'images': [],
            'attributes': []
        }
        
        product = self.env['woocommerce.product'].create_from_wc_data(
            wc_data, self.connection.id
        )
        
        self.assertEqual(product.wc_product_id, 456)
        self.assertEqual(product.name, 'New Product')
        self.assertEqual(product.wc_sku, 'SKU-123')

    @patch('odoo.addons.woocommerce_integration.models.woocommerce_connection.WooCommerceConnection.update_product')
    def test_action_sync_to_woocommerce(self, mock_update):
        mock_update.return_value = {'id': 123, 'name': 'Test Product'}
        result = self.wc_product.action_sync_to_woocommerce()
        self.assertEqual(result['params']['type'], 'success')

    def test_prepare_partial_woocommerce_data(self):
        self.wc_product.name = 'Test Product'
        self.wc_product.regular_price = 29.99
        self.wc_product.sale_price = 24.99
        self.wc_product.status = 'publish'
        self.wc_product.wc_sku = 'TEST-123'
        
        data = self.wc_product._prepare_partial_woocommerce_data(
            ['name', 'regular_price', 'sale_price', 'status', 'wc_sku']
        )
        
        self.assertEqual(data['name'], 'Test Product')
        self.assertEqual(data['regular_price'], '29.99')
        self.assertEqual(data['sale_price'], '24.99')
        self.assertEqual(data['status'], 'publish')
        self.assertEqual(data['sku'], 'TEST-123')

