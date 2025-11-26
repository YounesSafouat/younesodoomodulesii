from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError
from unittest.mock import patch, MagicMock
import json


class TestWooCommerceConnection(TransactionCase):

    def setUp(self):
        super(TestWooCommerceConnection, self).setUp()
        self.connection = self.env['woocommerce.connection'].create({
            'name': 'Test Store',
            'store_url': 'https://teststore.com',
            'consumer_key': 'test_key',
            'consumer_secret': 'test_secret',
            'api_version': 'v3',
        })

    def test_connection_creation(self):
        self.assertEqual(self.connection.name, 'Test Store')
        self.assertEqual(self.connection.store_url, 'https://teststore.com')
        self.assertTrue(self.connection.active)

    def test_get_api_url(self):
        url = self.connection._get_api_url('products')
        self.assertEqual(url, 'https://teststore.com/wp-json/wc/v3/products')
        
        url = self.connection._get_api_url('/products')
        self.assertEqual(url, 'https://teststore.com/wp-json/wc/v3/products')

    def test_get_auth_headers(self):
        headers = self.connection._get_auth_headers()
        self.assertIn('Authorization', headers)
        self.assertIn('Content-Type', headers)
        self.assertEqual(headers['Content-Type'], 'application/json')
        self.assertTrue(headers['Authorization'].startswith('Basic '))

    @patch('requests.get')
    def test_test_connection_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {'X-WP-Total': '100'}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        result = self.connection.test_connection()
        self.assertEqual(self.connection.connection_status, 'success')
        self.assertFalse(self.connection.connection_error)

    @patch('requests.get')
    def test_test_connection_failure(self, mock_get):
        mock_get.side_effect = Exception('Connection failed')
        
        result = self.connection.test_connection()
        self.assertEqual(self.connection.connection_status, 'error')
        self.assertTrue(self.connection.connection_error)

    @patch('requests.get')
    def test_get_products(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{'id': 1, 'name': 'Test Product'}]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        products = self.connection.get_products(page=1, per_page=10)
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]['name'], 'Test Product')

    @patch('requests.get')
    def test_get_product(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'id': 1, 'name': 'Test Product'}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        product = self.connection.get_product(1)
        self.assertEqual(product['id'], 1)
        self.assertEqual(product['name'], 'Test Product')

    @patch('requests.get')
    def test_get_categories(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{'id': 1, 'name': 'Category 1'}]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        categories = self.connection.get_categories()
        self.assertEqual(len(categories), 1)

    @patch('requests.post')
    def test_create_product(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {'id': 123, 'name': 'New Product'}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response
        
        product_data = {
            'name': 'New Product',
            'type': 'simple',
            'regular_price': '29.99'
        }
        
        result = self.connection.create_product(product_data)
        self.assertEqual(result['id'], 123)

    @patch('requests.put')
    @patch('requests.get')
    def test_update_product(self, mock_get, mock_put):
        existing_product = {'id': 1, 'name': 'Old Name', 'regular_price': '19.99'}
        mock_get_response = MagicMock()
        mock_get_response.json.return_value = existing_product
        mock_get_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_get_response
        
        mock_put_response = MagicMock()
        mock_put_response.status_code = 200
        mock_put_response.json.return_value = {'id': 1, 'name': 'New Name'}
        mock_put_response.raise_for_status = MagicMock()
        mock_put.return_value = mock_put_response
        
        product_data = {'name': 'New Name'}
        result = self.connection.update_product(1, product_data)
        self.assertEqual(result['name'], 'New Name')

    def test_compute_total_products(self):
        self.connection.total_products = 50
        self.assertEqual(self.connection.total_products, 50)

    def test_compute_import_progress(self):
        self.connection.import_progress_count_persisted = 25
        self.connection.import_total_count_persisted = 100
        self.connection.import_in_progress_persisted = True
        
        self.connection._compute_import_progress()
        self.assertEqual(self.connection.import_progress, 25.0)
        self.assertEqual(self.connection.import_progress_width, '25.0%')

