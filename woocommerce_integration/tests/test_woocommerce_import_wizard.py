from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError
from unittest.mock import patch, MagicMock


class TestWooCommerceImportWizard(TransactionCase):

    def setUp(self):
        super(TestWooCommerceImportWizard, self).setUp()
        self.connection = self.env['woocommerce.connection'].create({
            'name': 'Test Store',
            'store_url': 'https://teststore.com',
            'consumer_key': 'test_key',
            'consumer_secret': 'test_secret',
            'api_version': 'v3',
            'connection_status': 'success',
            'total_products': 100,
        })

    def test_wizard_creation(self):
        wizard = self.env['woocommerce.import.wizard'].create({
            'connection_id': self.connection.id,
            'import_limit': 50,
            'batch_size': 10,
        })
        
        self.assertEqual(wizard.connection_id.id, self.connection.id)
        self.assertEqual(wizard.import_limit, 50)
        self.assertEqual(wizard.batch_size, 10)
        self.assertEqual(wizard.state, 'draft')

    def test_compute_total_batches(self):
        wizard = self.env['woocommerce.import.wizard'].create({
            'connection_id': self.connection.id,
            'import_limit': 50,
            'batch_size': 10,
        })
        
        wizard._compute_total_batches()
        self.assertEqual(wizard.total_batches, 5)

    def test_onchange_batch_size_limit(self):
        wizard = self.env['woocommerce.import.wizard'].create({
            'connection_id': self.connection.id,
            'batch_size': 150,
        })
        
        result = wizard._onchange_batch_size()
        self.assertEqual(wizard.batch_size, 100)
        self.assertIsNotNone(result)
        self.assertIn('warning', result)

    def test_default_get(self):
        defaults = self.env['woocommerce.import.wizard'].default_get(['connection_id', 'batch_size'])
        self.assertIsInstance(defaults, dict)

    @patch('odoo.addons.woocommerce_integration.models.woocommerce_import_wizard.WooCommerceImportWizard._start_background_import_logic')
    def test_start_background_import(self, mock_start):
        wizard = self.env['woocommerce.import.wizard'].create({
            'connection_id': self.connection.id,
            'import_limit': 10,
            'batch_size': 5,
        })
        
        wizard.action_start_import()
        mock_start.assert_called_once()

    def test_import_settings_validation(self):
        wizard = self.env['woocommerce.import.wizard'].create({
            'connection_id': self.connection.id,
            'import_categories': True,
            'import_images': True,
            'import_attributes': True,
        })
        
        self.assertTrue(wizard.import_categories)
        self.assertTrue(wizard.import_images)
        self.assertTrue(wizard.import_attributes)

    def test_progress_computation(self):
        wizard = self.env['woocommerce.import.wizard'].create({
            'connection_id': self.connection.id,
            'progress_current': 25,
            'progress_total': 100,
        })
        
        wizard._compute_progress_percentage()
        self.assertEqual(wizard.progress_percentage, 25.0)

    def test_wizard_without_connection(self):
        wizard = self.env['woocommerce.import.wizard'].new({
            'import_limit': 10,
        })
        
        with self.assertRaises(UserError):
            wizard.action_start_import()

