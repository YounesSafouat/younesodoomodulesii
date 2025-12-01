import requests
import json
import base64
import time
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class WooCommerceConnection(models.Model):
    _name = 'woocommerce.connection'
    _description = 'WooCommerce Connection'
    _order = 'name'

    name = fields.Char(
        string='Connection Name',
        required=True,
        help='Name to identify this WooCommerce connection'
    )
    
    store_url = fields.Char(
        string='Store URL',
        required=True,
        help='Your WooCommerce store URL (e.g., https://yourstore.com)'
    )
    
    consumer_key = fields.Char(
        string='Consumer Key',
        required=True,
        help='WooCommerce API Consumer Key'
    )
    
    consumer_secret = fields.Char(
        string='Consumer Secret',
        required=True,
        help='WooCommerce API Consumer Secret'
    )
    
    wp_username = fields.Char(
        string='WordPress Username',
        help='WordPress username for media upload authentication'
    )
    wp_application_password = fields.Char(
        string='WordPress Application Password',
        help='WordPress Application Password for media upload (format: xxxx xxxx xxxx xxxx xxxx xxxx)'
    )
    
    image_upload_method = fields.Selection([
        ('wordpress_media', 'WordPress Media Library (Recommended)'),
        ('woocommerce_base64', 'WooCommerce API Base64 (Simpler, no WP auth needed)'),
    ], string='Image Upload Method', default='woocommerce_base64',
       help='Choose how to upload images:\n'
            '- WordPress Media Library: More reliable, requires WP credentials\n'
            '- WooCommerce API Base64: Simpler, but may have size limitations')
    
    default_sync_direction = fields.Selection([
        ('odoo_to_wc', 'Odoo → WooCommerce'),
        ('wc_to_odoo', 'WooCommerce → Odoo'),
        ('bidirectional', 'Bidirectional'),
    ], string='Default Sync Direction', default='bidirectional',
       help='Default sync direction for new products')

    import_variants = fields.Boolean(
        string='Import Product Variants',
        default=True,
        help='Import WooCommerce product variations as Odoo variants'
    )
    
    auto_create_variants = fields.Boolean(
        string='Auto-Create Variants',
        default=True,
        help='Automatically create Odoo variants when importing variable products'
    )
    
    variant_sync_enabled = fields.Boolean(
        string='Enable Variant Sync',
        default=True,
        help='Enable synchronization of variant-specific data (price, stock, SKU)'
    )
    
    variant_attribute_mapping = fields.Selection([
        ('auto', 'Auto-Map by Name'),
        ('manual', 'Manual Mapping Required'),
        ('skip', 'Skip Variant Creation'),
    ], string='Variant Attribute Mapping', default='auto',
       help='How to map WooCommerce attributes to Odoo attributes:\n'
            '- Auto-Map by Name: Automatically match attributes by name\n'
            '- Manual Mapping Required: Require user to map attributes manually\n'
            '- Skip Variant Creation: Import as simple products only')
    
    api_version = fields.Selection([
        ('v3', 'v3'),
        ('v2', 'v2'),
        ('v1', 'v1'),
    ], string='API Version', default='v3', required=True)
    
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Check to enable this connection'
    )
    
    last_sync = fields.Datetime(
        string='Last Sync',
        readonly=True,
        help='Last time products were synchronized'
    )
    
    total_products = fields.Integer(
        string='Total Products',
        compute='_compute_total_products',
        help='Total number of products in WooCommerce store'
    )
    
    connection_status = fields.Selection([
        ('not_tested', 'Not Tested'),
        ('success', 'Connected'),
        ('error', 'Connection Error'),
    ], string='Connection Status', default='not_tested', readonly=True)
    
    connection_error = fields.Text(
        string='Connection Error',
        readonly=True,
        help='Last connection error message'
    )
    
    field_mapping_ids = fields.One2many(
        'woocommerce.field.mapping',
        'connection_id',
        string='Field Mappings',
        help='Field mappings for this WooCommerce connection'
    )
    
    product_ids = fields.One2many(
        'woocommerce.product',
        'connection_id',
        string='Products',
        help='Products linked to this WooCommerce connection'
    )
    

    import_in_progress = fields.Boolean(
        string='Import In Progress',
        default=False,
        help='Indicates if an import is currently running'
    )
    
    import_progress = fields.Float(
        string='Import Progress (%)',
        compute='_compute_import_progress',
        help='Progress of the current import operation'
    )
    
    import_progress_width = fields.Char(
        string='Progress Bar Width',
        compute='_compute_import_progress',
        help='Progress bar width for display'
    )
    
    import_status = fields.Char(
        string='Import Status',
        compute='_compute_import_status',
        help='Current status of the import'
    )
    

    import_in_progress_persisted = fields.Boolean(
        string='Import In Progress (Persisted)',
        default=False,
        help='Indicates if import is currently running (persisted)'
    )
    
    import_progress_count_persisted = fields.Integer(
        string='Import Progress Count',
        default=0,
        help='Number of products imported so far (persisted)'
    )
    
    import_total_count_persisted = fields.Integer(
        string='Import Total Count',
        default=0,
        help='Total number of products to import (persisted)'
    )
    
    discovered_wc_fields = fields.Text(
        string='Discovered WooCommerce Fields',
        help='JSON data of discovered WooCommerce fields from the store'
    )
    


    active_import_wizard_id = fields.Integer(
        string='Active Import Wizard ID',
        help='ID of current active import wizard for background processing (stored as integer, not relation)'
    )
    
    import_batch_size = fields.Integer(
        string='Import Batch Size',
        default=25,
        help='Batch size for current import'
    )
    
    import_settings = fields.Text(
        string='Import Settings',
        help='JSON settings for current import (categories, images, attributes, etc.)'
    )
    
    import_notification_sent = fields.Boolean(
        string='Import Notification Sent',
        default=False,
        help='Track if completion notification has been sent to avoid duplicates'
    )
    
    import_log = fields.Text(
        string='Import Log',
        help='Detailed log of import operations (last 10000 characters). This log updates automatically during import operations.'
    )
    
    import_cron_status = fields.Char(
        string='Import Cron Status',
        compute='_compute_import_cron_status',
        help='Status of the import cron job. Shows if the cron job exists and is active.'
    )
    
    @api.depends('name', 'import_in_progress_persisted')
    def _compute_import_cron_status(self):
        """Compute the status of the import cron job"""
        for connection in self:
            if not connection.import_in_progress_persisted:
                connection.import_cron_status = 'No import in progress'
            else:
                cron_name = f'WooCommerce Import - {connection.name}'
                # Use a fresh search to ensure we get the latest data
                cron = self.env['ir.cron'].sudo().with_context(prefetch_fields=False).search([('name', '=', cron_name)], limit=1)
                if cron.exists():
                    status = 'Active' if cron.active else 'Inactive'
                    connection.import_cron_status = f'✅ Cron job exists: {status} (ID: {cron.id}, runs every {cron.interval_number} {cron.interval_type})'
                else:
                    connection.import_cron_status = '⚠️ Cron job missing - Click "Resume Import" to recreate it'
    
    @api.depends('import_progress_count_persisted', 'import_total_count_persisted', 'import_in_progress_persisted')
    def _compute_import_progress(self):
        """Compute import progress from persisted fields"""
        for connection in self:
            progress = 0
            if connection.import_total_count_persisted > 0:
                progress = (connection.import_progress_count_persisted / connection.import_total_count_persisted) * 100
            
            connection.import_progress = progress
            connection.import_in_progress = connection.import_in_progress_persisted
            connection.import_progress_width = f"{progress}%"
    
    @api.depends('import_progress_count_persisted', 'import_total_count_persisted', 'import_in_progress_persisted')
    def _compute_import_status(self):
        """Compute import status message from persisted fields"""
        for connection in self:
            if connection.import_in_progress_persisted and connection.import_total_count_persisted > 0:
                total = connection.import_total_count_persisted
                imported = connection.import_progress_count_persisted
                status = f"Imported: {imported}/{total} products - Processing..."
            else:
                status = "No import in progress"
            
            connection.import_status = status
    
    @api.depends('store_url', 'consumer_key', 'consumer_secret')
    def _compute_total_products(self):
        """Compute total products from WooCommerce"""
        for record in self:
            if record.active and record.store_url and record.consumer_key and record.consumer_secret:
                try:
                    total = record._test_connection_and_get_products_count()
                    record.total_products = total
                except Exception:
                    record.total_products = 0
            else:
                record.total_products = 0
    
    def _get_api_url(self, endpoint=''):
        """Get the full API URL for the given endpoint"""
        self.ensure_one()
        base_url = self.store_url.rstrip('/')
        if endpoint.startswith('/'):
            endpoint = endpoint[1:]
        return f"{base_url}/wp-json/wc/{self.api_version}/{endpoint}"
    
    def _get_auth_headers(self):
        """Get authentication headers for WooCommerce API"""
        self.ensure_one()
        credentials = f"{self.consumer_key}:{self.consumer_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        return {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/json',
            'User-Agent': 'Odoo-WooCommerce-Integration/1.0'
        }
    
    def _get_wp_auth_headers(self):
        """Get authentication headers for WordPress REST API"""
        self.ensure_one()
        if not self.wp_username or not self.wp_application_password:
            raise UserError(_('WordPress username and application password are required for media upload'))
        
        clean_password = self.wp_application_password.replace(' ', '')
        credentials = f"{self.wp_username}:{clean_password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        return {
            'Authorization': f'Basic {encoded_credentials}',
            'User-Agent': 'Odoo-WooCommerce-Integration/1.0'
        }
    
    def test_wordpress_auth(self):
        """Test WordPress authentication for media upload"""
        self.ensure_one()
        
        if not self.wp_username or not self.wp_application_password:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('WordPress Auth Test'),
                    'message': _('WordPress username and application password are required. Please configure them first.'),
                    'type': 'warning',
                    'sticky': True,
                }
            }
        
        try:
            store_url = self.store_url.rstrip('/')
            wp_api_url = f"{store_url}/wp-json/wp/v2/users/me"
            
            headers = self._get_wp_auth_headers()
            
            _logger.info(f"Testing WordPress authentication for user: {self.wp_username}")
            _logger.info(f"WordPress API URL: {wp_api_url}")
            
            response = requests.get(wp_api_url, headers=headers, timeout=30)
            
            if response.status_code == 401:
                _logger.error("WordPress authentication failed (401)")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('WordPress Auth Test Failed'),
                        'message': _('WordPress authentication failed. Please check:\n1. Username is correct\n2. Application password format (xxxx xxxx xxxx xxxx xxxx xxxx)\n3. User has proper permissions\n4. Application password is not expired'),
                        'type': 'danger',
                        'sticky': True,
                    }
                }
            
            response.raise_for_status()
            user_data = response.json()
            
            _logger.info(f"WordPress authentication successful for user: {user_data.get('name', 'Unknown')}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('WordPress Auth Test Successful'),
                    'message': _('WordPress authentication successful! User: %s') % user_data.get('name', 'Unknown'),
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except requests.exceptions.RequestException as e:
            _logger.error(f"WordPress authentication test failed: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('WordPress Auth Test Failed'),
                    'message': _('WordPress authentication test failed: %s') % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
    
    def test_connection(self):
        """Test the WooCommerce API connection"""
        self.ensure_one()
        
        if not all([self.store_url, self.consumer_key, self.consumer_secret]):
            raise ValidationError(_('Please provide Store URL, Consumer Key, and Consumer Secret'))
        
        try:
            url = self._get_api_url('system_status')
            headers = self._get_auth_headers()
            
            response = requests.get(url, headers=headers, timeout=600)
            response.raise_for_status()
            
            self.connection_status = 'success'
            self.connection_error = False
            
            total_products = self._test_connection_and_get_products_count()
            
            message = _('Connection successful! Found %d products in your store.') % total_products
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Test'),
                    'message': message,
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            self.connection_status = 'error'
            self.connection_error = error_msg
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Test Failed'),
                    'message': _('Failed to connect to WooCommerce: %s') % error_msg,
                    'type': 'danger',
                    'sticky': True,
                }
            }
        except Exception as e:
            error_msg = str(e)
            self.connection_status = 'error'
            self.connection_error = error_msg
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Test Failed'),
                    'message': _('Unexpected error: %s') % error_msg,
                    'type': 'danger',
                    'sticky': True,
                }
            }
    
    def _test_connection_and_get_products_count(self):
        """Test connection and get products count"""
        self.ensure_one()
        
        url = self._get_api_url('products')
        headers = self._get_auth_headers()
        
        params = {
            'per_page': 1,
            'page': 1,
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        
        total_products = int(response.headers.get('X-WP-Total', 0))
        return total_products
    
    def get_products(self, page=1, per_page=100, **kwargs):
        """Get products from WooCommerce with all attributes included"""
        self.ensure_one()
        
        url = self._get_api_url('products')
        headers = self._get_auth_headers()
        
        params = {
            'page': page,
            'per_page': per_page,
        }
        params.update(kwargs)
        


        include_params = {
            'include_meta': 'true',
            'include_attributes': 'true',
            'include_variations': 'true',
            'include_images': 'true',
            'include_categories': 'true',
            'include_tags': 'true',
        }
        params.update(include_params)
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=600)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error fetching products from WooCommerce: {e}")
            raise UserError(_('Failed to fetch products from WooCommerce: %s') % str(e))
    
    def get_product(self, product_id):
        """Get a specific product from WooCommerce with all attributes included"""
        self.ensure_one()
        
        url = self._get_api_url(f'products/{product_id}')
        headers = self._get_auth_headers()
        

        params = {
            'include_meta': 'true',
            'include_attributes': 'true',
            'include_variations': 'true',
            'include_images': 'true',
            'include_categories': 'true',
            'include_tags': 'true',
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=600)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error fetching product {product_id} from WooCommerce: {e}")
            raise UserError(_('Failed to fetch product from WooCommerce: %s') % str(e))
    
    def get_categories(self, page=1, per_page=100):
        """Get product categories from WooCommerce"""
        self.ensure_one()
        
        url = self._get_api_url('products/categories')
        headers = self._get_auth_headers()
        
        params = {
            'page': page,
            'per_page': per_page,
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error fetching categories from WooCommerce: {e}")
            raise UserError(_('Failed to fetch categories from WooCommerce: %s') % str(e))
    
    def get_category(self, category_id):
        """Get a single category from WooCommerce"""
        self.ensure_one()
        
        url = self._get_api_url(f'products/categories/{category_id}')
        headers = self._get_auth_headers()
        
        try:
            response = requests.get(url, headers=headers, timeout=600)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error fetching category {category_id} from WooCommerce: {e}")
            raise UserError(_('Failed to fetch category from WooCommerce: %s') % str(e))
    
    def get_attributes(self, page=1, per_page=100):
        """Get product attributes from WooCommerce"""
        self.ensure_one()
        
        url = self._get_api_url('products/attributes')
        headers = self._get_auth_headers()
        
        params = {
            'page': page,
            'per_page': per_page,
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=600)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error fetching attributes from WooCommerce: {e}")
            raise UserError(_('Failed to fetch attributes from WooCommerce: %s') % str(e))
    
    def get_attribute_terms(self, attribute_id, page=1, per_page=100):
        """Get terms for a specific attribute from WooCommerce"""
        self.ensure_one()
        
        url = self._get_api_url(f'products/attributes/{attribute_id}/terms')
        headers = self._get_auth_headers()
        
        params = {
            'page': page,
            'per_page': per_page,
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error fetching attribute terms for attribute {attribute_id} from WooCommerce: {e}")
            raise UserError(_('Failed to fetch attribute terms from WooCommerce: %s') % str(e))
    
    def get_product_variations(self, product_id, page=1, per_page=100):
        """Get variations for a variable product from WooCommerce"""
        self.ensure_one()
        
        url = self._get_api_url(f'products/{product_id}/variations')
        headers = self._get_auth_headers()
        
        params = {
            'page': page,
            'per_page': per_page,
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=600)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error fetching variations for product {product_id} from WooCommerce: {e}")
            raise UserError(_('Failed to fetch variations from WooCommerce: %s') % str(e))
    
    def get_product_variation(self, product_id, variation_id):
        """Get a specific variation from WooCommerce"""
        self.ensure_one()
        
        url = self._get_api_url(f'products/{product_id}/variations/{variation_id}')
        headers = self._get_auth_headers()
        
        try:
            response = requests.get(url, headers=headers, timeout=600)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error fetching variation {variation_id} for product {product_id} from WooCommerce: {e}")
            raise UserError(_('Failed to fetch variation from WooCommerce: %s') % str(e))
    
    def action_import_categories(self):
        """Import all categories from WooCommerce"""
        self.ensure_one()
        
        if self.connection_status != 'success':
            raise UserError(_('Please test the connection first before importing categories.'))
        
        try:
            categories_data = self.get_categories(per_page=100)
            
            if not categories_data:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('No Categories'),
                        'message': _('No categories found in WooCommerce'),
                        'type': 'warning',
                    }
                }
            
            WooCategory = self.env['woocommerce.category']
            created_count = 0
            updated_count = 0
            
            for cat_data in categories_data:
                existing = WooCategory.search([
                    ('wc_category_id', '=', cat_data['id']),
                    ('connection_id', '=', self.id)
                ], limit=1)
                
                vals = {
                    'name': cat_data.get('name', ''),
                    'wc_category_id': cat_data['id'],
                    'connection_id': self.id,
                    'wc_slug': cat_data.get('slug', ''),
                    'description': cat_data.get('description', ''),
                    'wc_count': cat_data.get('count', 0),
                    'wc_parent_id': cat_data.get('parent', 0),
                    'last_sync': fields.Datetime.now(),
                    'sync_status': 'synced',
                }
                
                if cat_data.get('image'):
                    vals['wc_image_url'] = cat_data['image'].get('src', '')
                
                if existing:
                    existing.write(vals)
                    updated_count += 1
                else:
                    WooCategory.create(vals)
                    created_count += 1
            

            for wc_cat in WooCategory.search([('connection_id', '=', self.id), ('wc_parent_id', '!=', 0)]):
                parent = WooCategory.search([
                    ('wc_category_id', '=', wc_cat.wc_parent_id),
                    ('connection_id', '=', self.id)
                ], limit=1)
                if parent:
                    wc_cat.write({'parent_id': parent.id})
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Categories Imported'),
                    'message': _('Created: %d, Updated: %d categories') % (created_count, updated_count),
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            _logger.error(f"Error importing categories: {str(e)}")
            raise UserError(_('Failed to import categories: %s') % str(e))
    
    def action_import_products(self):
        """Action to import products from WooCommerce"""
        self.ensure_one()
        
        if self.connection_status != 'success':
            raise UserError(_('Please test the connection first before importing products.'))
        
        return {
            'name': _('Import Products from WooCommerce'),
            'type': 'ir.actions.act_window',
            'res_model': 'woocommerce.import.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_connection_id': self.id,
                'default_total_products': self.total_products,
            }
        }
    
    def action_import_odoo_products(self):
        """Action to import Odoo products to WooCommerce"""
        self.ensure_one()
        
        if self.connection_status != 'success':
            raise UserError(_('Please test the connection first before importing products.'))
        
        return {
            'name': _('Import Odoo Products to WooCommerce'),
            'type': 'ir.actions.act_window',
            'res_model': 'odoo.to.woocommerce.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_connection_id': self.id,
            }
        }
    
    def action_view_field_mappings(self):
        """View field mappings for this connection"""
        self.ensure_one()
        return {
            'name': _('Field Mappings'),
            'type': 'ir.actions.act_window',
            'res_model': 'woocommerce.field.mapping',
            'view_mode': 'list,form',
            'domain': [('connection_id', '=', self.id)],
            'context': {
                'default_connection_id': self.id,
                'search_default_active': 1,
            }
        }
    
    def action_create_default_mappings(self):
        """Create default field mappings for this connection"""
        self.ensure_one()
        

        existing_mappings = self.env['woocommerce.field.mapping'].search([
            ('connection_id', '=', self.id)
        ])
        
        if existing_mappings:
            raise UserError(_('Field mappings already exist for this connection. Please delete existing mappings first if you want to recreate them.'))
        

        default_mappings = self.env['woocommerce.field.mapping'].get_default_mappings()
        for mapping_data in default_mappings:
            mapping_data['connection_id'] = self.id
            self.env['woocommerce.field.mapping'].create(mapping_data)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Default Mappings Created'),
                'message': _('Default field mappings have been created for this connection.'),
                'type': 'success',
            }
        }
    
    def action_get_woocommerce_fields(self):
        """Get actual WooCommerce product fields from the store"""
        self.ensure_one()
        
        if self.connection_status != 'success':
            raise UserError(_('Please test the connection first before getting WooCommerce fields.'))
        
        try:

            products = self.get_products(page=1, per_page=10)
            
            if not products:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('No Products Found'),
                        'message': _('No products found in WooCommerce store to analyze fields.'),
                        'type': 'warning',
                    }
                }
            

            try:
                attributes_data = self.get_attributes(page=1, per_page=100)
            except Exception as e:
                _logger.warning(f"Failed to get attributes: {e}")
                attributes_data = []
            

            all_fields = set()
            custom_fields = set()
            
            def extract_fields(data, prefix=''):
                """Recursively extract all fields from the product data"""
                fields = []
                for key, value in data.items():
                    if isinstance(value, dict):

                        nested_fields = extract_fields(value, f"{prefix}{key}.")
                        fields.extend(nested_fields)
                    elif isinstance(value, list) and value and isinstance(value[0], dict):

                        if key in ['images', 'categories', 'tags', 'attributes', 'default_attributes', 'variations', 'meta_data']:
                            if key == 'meta_data':

                                for meta_item in value:
                                    if isinstance(meta_item, dict) and 'key' in meta_item:
                                        meta_key = meta_item.get('key', '')
                                        meta_value = meta_item.get('value', '')
                                        field_name = f"{prefix}meta_data.{meta_key}"
                                        field_label = f"Custom: {meta_key.replace('_', ' ').title()}"
                                        fields.append((field_name, field_label))

                                        custom_fields.add((field_name, field_label))
                            elif key == 'attributes':

                                for attr_item in value:
                                    if isinstance(attr_item, dict) and 'name' in attr_item:
                                        attr_name = attr_item.get('name', '')
                                        attr_slug = attr_item.get('slug', '')
                                        attr_id = attr_item.get('id', '')

                                        field_name = f"{prefix}attributes.{attr_slug}"
                                        field_label = f"Attribute: {attr_name}"
                                        fields.append((field_name, field_label))
                                        custom_fields.add((field_name, field_label))
                                        

                                        field_name_values = f"{prefix}attributes.{attr_slug}.options"
                                        field_label_values = f"Attribute {attr_name} Values"
                                        fields.append((field_name_values, field_label_values))
                                        custom_fields.add((field_name_values, field_label_values))
                            else:
                                fields.append((f"{prefix}{key}", key.replace('_', ' ').title()))
                    else:

                        field_name = f"{prefix}{key}"
                        field_label = key.replace('_', ' ').title()
                        fields.append((field_name, field_label))
                        all_fields.add((field_name, field_label))
                return fields
            

            for product in products:
                product_fields = extract_fields(product)
                all_fields.update(product_fields)
            

            for attr in attributes_data:
                if isinstance(attr, dict):
                    attr_name = attr.get('name', '')
                    attr_slug = attr.get('slug', '')
                    attr_id = attr.get('id', '')
                    
                    if attr_slug:

                        field_name = f"attributes.{attr_slug}"
                        field_label = f"Attribute: {attr_name}"
                        all_fields.add((field_name, field_label))
                        custom_fields.add((field_name, field_label))
                        

                        field_name_values = f"attributes.{attr_slug}.options"
                        field_label_values = f"Attribute {attr_name} Values"
                        all_fields.add((field_name_values, field_label_values))
                        custom_fields.add((field_name_values, field_label_values))
                        

                        field_name_id = f"attributes.{attr_id}"
                        field_label_id = f"Attribute ID {attr_id}: {attr_name}"
                        all_fields.add((field_name_id, field_label_id))
                        custom_fields.add((field_name_id, field_label_id))
            

            wc_fields = sorted(list(all_fields))
            custom_fields_list = sorted(list(custom_fields))
            

            import json
            discovered_data = {
                'all_fields': wc_fields,
                'custom_fields': custom_fields_list,
                'discovery_date': fields.Datetime.now().isoformat(),
                'products_analyzed': len(products)
            }
            
            self.write({
                'discovered_wc_fields': json.dumps(discovered_data)
            })
            

            attribute_fields = [f for f in wc_fields if f[0].startswith('attributes.')]
            meta_fields = [f for f in wc_fields if f[0].startswith('meta_data.')]
            regular_fields = [f for f in wc_fields if not f[0].startswith(('attributes.', 'meta_data.'))]
            
            field_summary = f'Discovered {len(wc_fields)} WooCommerce fields:\n'
            field_summary += f'  - {len(regular_fields)} regular fields\n'
            field_summary += f'  - {len(attribute_fields)} WooCommerce attributes\n'
            field_summary += f'  - {len(meta_fields)} custom meta fields\n\n'
            

            if regular_fields:
                field_summary += 'Regular Fields:\n'
                field_summary += '\n'.join([f'  {field[0]}: {field[1]}' for field in regular_fields[:10]])
                if len(regular_fields) > 10:
                    field_summary += f'\n  ... and {len(regular_fields) - 10} more regular fields'
                field_summary += '\n\n'
            

            if attribute_fields:
                field_summary += 'WooCommerce Attributes:\n'
                field_summary += '\n'.join([f'  {field[0]}: {field[1]}' for field in attribute_fields[:15]])
                if len(attribute_fields) > 15:
                    field_summary += f'\n  ... and {len(attribute_fields) - 15} more attributes'
                field_summary += '\n\n'
            

            if meta_fields:
                field_summary += 'Custom Meta Fields:\n'
                field_summary += '\n'.join([f'  {field[0]}: {field[1]}' for field in meta_fields[:15]])
                if len(meta_fields) > 15:
                    field_summary += f'\n  ... and {len(meta_fields) - 15} more custom fields'
            
            self.write({
                'connection_error': field_summary
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('WooCommerce Fields Discovered'),
                    'message': _('Found %d total fields (%d regular + %d attributes + %d custom) in WooCommerce store. Check connection details for the complete list.') % (
                        len(wc_fields), len(regular_fields), len(attribute_fields), len(meta_fields)
                    ),
                    'type': 'success',
                    'sticky': True,
                }
            }
            
        except Exception as e:
            _logger.error(f"Error getting WooCommerce fields: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error Getting Fields'),
                    'message': _('Error getting WooCommerce fields: %s') % str(e),
                    'type': 'danger',
                }
            }
    
    def create_product(self, product_data):
        """Create a new product in WooCommerce"""
        self.ensure_one()
        


        product_data = product_data.copy()
        product_data.pop('id', None)
        product_data.pop('wc_product_id', None)
        

        if 'sku' in product_data and product_data['sku']:
            original_sku = product_data['sku']

            product_data['sku'] = f"{original_sku}-{int(time.time())}"
        
        url = self._get_api_url('products')
        headers = self._get_auth_headers()
        
        try:
            _logger.info(f"Creating WooCommerce product with data: {product_data}")
            response = requests.post(url, headers=headers, json=product_data, timeout=600)
            
            if response.status_code == 400:
                try:
                    error_details = response.json()
                    

                    if error_details.get('code') == 'product_invalid_sku' and error_details.get('data', {}).get('unique_sku'):
                        suggested_sku = error_details['data']['unique_sku']
                        _logger.info(f"Using WooCommerce suggested unique SKU: {suggested_sku}")
                        product_data['sku'] = suggested_sku
                        

                        retry_response = requests.post(url, headers=headers, json=product_data, timeout=600)
                        if retry_response.status_code == 200 or retry_response.status_code == 201:
                            return retry_response.json()
                    
                    _logger.error(f"WooCommerce 400 Error during product creation: {error_details}")

                    error_message = self._parse_woocommerce_error(error_details)
                    raise UserError(error_message)
                except UserError:
                    raise
                except:
                    _logger.error(f"WooCommerce 400 Error during product creation: {response.text}")

                    error_message = self._parse_woocommerce_error_text(response.text)
                    raise UserError(error_message)
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error creating product in WooCommerce: {e}")
            raise UserError(_('Failed to create product in WooCommerce: %s') % str(e))
    
    def update_product(self, product_id, product_data):
        """Update an existing product in WooCommerce"""
        self.ensure_one()
        

        try:
            product_id = int(str(product_id).replace(',', '').replace(' ', ''))
        except (ValueError, TypeError):
            raise UserError(_('Invalid product ID: %s. Product ID must be a number.') % product_id)
        

        product_data = product_data.copy()
        product_data.pop('id', None)
        product_data.pop('wc_product_id', None)
        

        try:
            current_product = self.get_product(product_id)
            if current_product:

                _logger.info(f"BEFORE MERGE - Current product has {len(current_product.get('attributes', []))} attributes")
                _logger.info(f"BEFORE MERGE - Update data has {len(product_data.get('attributes', []))} attributes")
                

                merged_data = current_product.copy()
                merged_data.update(product_data)
                product_data = merged_data
                
                _logger.info(f"AFTER MERGE - Merged data has {len(product_data.get('attributes', []))} attributes")
                _logger.info(f"Merged update with existing data for product {product_id}")
        except Exception as e:
            _logger.warning(f"Failed to get current product data for merge: {e}")

        
        url = self._get_api_url(f'products/{product_id}')
        headers = self._get_auth_headers()
        
        try:
            _logger.info(f"Updating WooCommerce product {product_id} with data: {product_data}")
            response = requests.put(url, headers=headers, json=product_data, timeout=600)
            

            _logger.info(f"WooCommerce API Response - Status: {response.status_code}")
            if response.status_code not in [200, 201]:
                _logger.warning(f"WooCommerce API Response Text: {response.text}")
            
            if response.status_code == 400:
                try:
                    error_details = response.json()
                    _logger.error(f"WooCommerce 400 Error for product {product_id}: {error_details}")
                    

                    error_message = self._parse_woocommerce_error(error_details)
                    raise UserError(error_message)
                except UserError:
                    raise
                except:
                    _logger.error(f"WooCommerce 400 Error for product {product_id}: {response.text}")

                    error_message = self._parse_woocommerce_error_text(response.text)
                    raise UserError(error_message)
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error updating product {product_id} in WooCommerce: {e}")
            raise UserError(_('Failed to update product in WooCommerce: %s') % str(e))
    
    def delete_product(self, product_id):
        """Delete a product from WooCommerce"""
        self.ensure_one()
        
        url = self._get_api_url(f'products/{product_id}')
        headers = self._get_auth_headers()
        
        try:
            response = requests.delete(url, headers=headers, timeout=600)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error deleting product {product_id} from WooCommerce: {e}")
            raise UserError(_('Failed to delete product from WooCommerce: %s') % str(e))
    
    def action_create_order_webhook(self):
        """Create order webhook for this connection"""
        self.ensure_one()
        

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        webhook_url = f"{base_url}/woocommerce/webhook/{self.id}"
        

        webhook = self.env['woocommerce.order.webhook'].create({
            'name': f'Order Webhook - {self.name}',
            'connection_id': self.id,
            'webhook_url': webhook_url,
            'webhook_topic': 'order.created',
            'auto_create_odoo_order': True,
            'auto_create_customer': True,
            'order_prefix': 'WC-',
            'active': True,
        })
        
        return {
            'name': _('Order Webhook Created'),
            'type': 'ir.actions.act_window',
            'res_model': 'woocommerce.order.webhook',
            'res_id': webhook.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def process_next_import_batch(self):
        """Process next batch of import - called by cron"""
        self.ensure_one()
        
        _logger.info(f'process_next_import_batch called for connection {self.name}, import_in_progress={self.import_in_progress_persisted}')
        
        if not self.import_in_progress_persisted:
            _logger.info(f'No import in progress for connection {self.name}')
            return
        

        wizard = None
        if self.active_import_wizard_id:
            wizard = self.env['woocommerce.import.wizard'].sudo().browse(self.active_import_wizard_id).exists()
        

        if not wizard:

            wizard = self.env['woocommerce.import.wizard'].sudo().search([
                ('connection_id', '=', self.id),
                ('state', '=', 'importing')
            ], order='create_date desc', limit=1)
            
            if wizard:
                self.write({'active_import_wizard_id': wizard.id})
                self.env.cr.commit()
        
        if wizard:

            try:
                wizard._import_single_batch_in_background()
            except Exception as e:
                _logger.error(f'Error processing batch for connection {self.name}: {e}')
                error_str = str(e).lower()
                is_concurrency_error = any(term in error_str for term in [
                    'serialize', 'concurrent update', 'could not serialize',
                    'current transaction is aborted'
                ])
                

                self.env.cr.rollback()
                

                if is_concurrency_error:
                    _logger.warning(f'Concurrency error in batch processing, will retry: {e}')
                    return
                

                if 'Record cannot be modified' not in str(e):
                    try:

                        self.env.cr.execute(
                            "SELECT id FROM woocommerce_connection WHERE id = %s FOR UPDATE NOWAIT",
                            (self.id,)
                        )
                        self.write({'import_in_progress_persisted': False})
                        self.env.cr.commit()
                    except Exception as lock_error:
                        self.env.cr.rollback()
                        _logger.warning(f'Could not update connection status: {lock_error}')
        else:


            total_imported = self.import_progress_count_persisted
            total_to_import = self.import_total_count_persisted
            
            if total_imported >= total_to_import:

                _logger.info(f'Import complete for connection {self.name}: {total_imported}/{total_to_import}')
                self.write({'import_in_progress_persisted': False})
                self.env.cr.commit()
                

                cron_name_pattern = f'WooCommerce Import - {self.name}%'
                crons = self.env['ir.cron'].sudo().search([
                    ('name', 'like', cron_name_pattern)
                ])
                if crons:
                    crons.unlink()
            else:
                _logger.warning(f'Import in progress for connection {self.name} but no wizard found. Progress: {total_imported}/{total_to_import}')
    
    def action_stop_import(self):
        """Manually stop a running import"""
        self.ensure_one()
        
        if not self.import_in_progress_persisted:
            raise UserError(_('No import is currently running.'))
        

        self.write({
            'import_in_progress_persisted': False,
        })
        self.env.cr.commit()
        

        cron_name = f'WooCommerce Import - {self.name}'
        cron = self.env['ir.cron'].sudo().search([('name', '=', cron_name)], limit=1)
        if cron:
            cron.sudo().unlink()
        

        try:
            wizard = self.env['woocommerce.import.wizard'].browse(self.active_import_wizard_id.id) if self.active_import_wizard_id else False
            if wizard and wizard.exists():
                wizard._append_to_connection_log(_('\n⚠️ Import stopped manually by user.'))
        except Exception as e:
            _logger.warning(f'Could not update wizard on stop: {e}')
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Import Stopped'),
                'message': _('The import has been stopped successfully.'),
                'type': 'success',
            }
        }
    
    def action_resume_import(self):
        """Manually resume a stuck import by recreating the cron job and triggering the next batch"""
        self.ensure_one()
        
        if not self.import_in_progress_persisted:
            raise UserError(_('No import is currently running. Nothing to resume.'))
        
        _logger.info(f'Manually resuming import for connection {self.name}')
        
        # Check if cron job exists, recreate if missing
        cron_name = f'WooCommerce Import - {self.name}'
        cron = self.env['ir.cron'].sudo().search([('name', '=', cron_name)], limit=1)
        
        if not cron:
            _logger.info(f'Import cron job missing, recreating for connection {self.name}')
            model_id = self.env['ir.model'].sudo().search([('model', '=', 'woocommerce.connection')], limit=1).id
            
            if not model_id:
                raise UserError(_('Could not find woocommerce.connection model'))
            
            cron = self.env['ir.cron'].sudo().create({
                'name': cron_name,
                'model_id': model_id,
                'state': 'code',
                'code': f'env["woocommerce.connection"].browse({self.id}).process_next_import_batch()',
                'interval_number': 1,
                'interval_type': 'minutes',
                'active': True,
                'user_id': self.env.uid,
            })
            # Commit the cron job creation to ensure it persists
            self.env.cr.commit()
            _logger.info(f'Recreated import cron job {cron_name} (ID: {cron.id}) for connection {self.name}')
        elif not cron.active:
            # Reactivate if it exists but is inactive
            cron.sudo().write({'active': True})
            self.env.cr.commit()
            _logger.info(f'Reactivated import cron job {cron_name} (ID: {cron.id}) for connection {self.name}')
        
        try:
            # Try to process the next batch immediately
            self.process_next_import_batch()
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Import Resumed'),
                    'message': _('The import cron job has been recreated/activated and batch processing has been triggered. The import will continue automatically every minute. Check the import log for progress.'),
                    'type': 'success',
                }
            }
        except Exception as e:
            _logger.error(f'Error resuming import: {e}')
            raise UserError(_('Failed to resume import: %s') % str(e))
    
    def _parse_woocommerce_error(self, error_details):
        """Parse WooCommerce API error and return user-friendly message"""
        try:

            error_message = error_details.get('message', 'Unknown error')
            

            error_code = error_details.get('code', '')
            error_data = error_details.get('data', {})
            

            if 'invalid' in error_code.lower() or 'invalid' in error_message.lower():
                params = error_data.get('params', {})
                details = error_data.get('details', {})
                

                friendly_msg = _('Invalid product data:\n\n')
                

                if 'status' in params or 'status' in details:
                    friendly_msg += _('• Status: Please select a valid status (Draft, Pending, Private, or Published)\n')
                
                if 'sku' in params or 'sku' in details:
                    friendly_msg += _('• SKU: The SKU may already exist or contain invalid characters\n')
                
                if 'price' in params or 'regular_price' in params:
                    friendly_msg += _('• Price: Please enter a valid price\n')
                

                if friendly_msg == _('Invalid product data:\n\n'):
                    friendly_msg += error_message
                else:
                    friendly_msg += _('\nOriginal error: %s') % error_message
                
                return friendly_msg
            

            return _('WooCommerce Error: %s') % error_message
            
        except Exception as e:
            _logger.warning(f"Error parsing WooCommerce error: {e}")
            return _('WooCommerce API Error: %s') % str(error_details)
    
    def _parse_woocommerce_error_text(self, error_text):
        """Parse WooCommerce API error text and return user-friendly message"""
        try:

            if '{' in error_text:
                import json

                start = error_text.find('{')
                end = error_text.rfind('}') + 1
                if start >= 0 and end > start:
                    json_str = error_text[start:end]
                    error_details = json.loads(json_str)
                    return self._parse_woocommerce_error(error_details)
            

            if 'status' in error_text.lower() and 'string' in error_text.lower():
                return _('Invalid Status: Please select a valid status (Draft, Pending, Private, or Published) in the product form.')
            
            return _('WooCommerce Error: %s') % error_text[:200]
            
        except Exception as e:
            _logger.warning(f"Error parsing WooCommerce error text: {e}")
            return _('WooCommerce API Error: %s') % error_text[:200]
    
    def get_coupons(self, page=1, per_page=100, **kwargs):
        """Get coupons from WooCommerce"""
        self.ensure_one()
        
        url = self._get_api_url('coupons')
        headers = self._get_auth_headers()
        
        params = {
            'page': page,
            'per_page': per_page,
        }
        params.update(kwargs)
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=600)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error fetching coupons from WooCommerce: {e}")
            raise UserError(_('Failed to fetch coupons from WooCommerce: %s') % str(e))
    
    def get_coupon(self, coupon_id):
        """Get a specific coupon from WooCommerce"""
        self.ensure_one()
        
        url = self._get_api_url(f'coupons/{coupon_id}')
        headers = self._get_auth_headers()
        
        try:
            response = requests.get(url, headers=headers, timeout=600)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error fetching coupon {coupon_id} from WooCommerce: {e}")
            raise UserError(_('Failed to fetch coupon from WooCommerce: %s') % str(e))
    
    def create_coupon(self, coupon_data):
        """Create a new coupon in WooCommerce"""
        self.ensure_one()
        
        coupon_data = coupon_data.copy()
        coupon_data.pop('id', None)
        coupon_data.pop('wc_coupon_id', None)
        
        url = self._get_api_url('coupons')
        headers = self._get_auth_headers()
        
        try:
            _logger.info(f"Creating WooCommerce coupon with data: {coupon_data}")
            response = requests.post(url, headers=headers, json=coupon_data, timeout=600)
            
            if response.status_code == 400:
                try:
                    error_details = response.json()
                    _logger.error(f"WooCommerce 400 Error during coupon creation: {error_details}")
                    error_message = self._parse_woocommerce_error(error_details)
                    raise UserError(error_message)
                except UserError:
                    raise
                except:
                    _logger.error(f"WooCommerce 400 Error during coupon creation: {response.text}")
                    error_message = self._parse_woocommerce_error_text(response.text)
                    raise UserError(error_message)
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error creating coupon in WooCommerce: {e}")
            raise UserError(_('Failed to create coupon in WooCommerce: %s') % str(e))
    
    def update_coupon(self, coupon_id, coupon_data):
        """Update an existing coupon in WooCommerce"""
        self.ensure_one()
        
        try:
            coupon_id = int(str(coupon_id).replace(',', '').replace(' ', ''))
        except (ValueError, TypeError):
            raise UserError(_('Invalid coupon ID: %s. Coupon ID must be a number.') % coupon_id)
        
        coupon_data = coupon_data.copy()
        coupon_data.pop('id', None)
        coupon_data.pop('wc_coupon_id', None)
        
        url = self._get_api_url(f'coupons/{coupon_id}')
        headers = self._get_auth_headers()
        
        try:
            _logger.info(f"Updating WooCommerce coupon {coupon_id} with data: {coupon_data}")
            response = requests.put(url, headers=headers, json=coupon_data, timeout=600)
            
            _logger.info(f"WooCommerce API Response - Status: {response.status_code}")
            if response.status_code not in [200, 201]:
                _logger.warning(f"WooCommerce API Response Text: {response.text}")
            
            if response.status_code == 400:
                try:
                    error_details = response.json()
                    _logger.error(f"WooCommerce 400 Error for coupon {coupon_id}: {error_details}")
                    error_message = self._parse_woocommerce_error(error_details)
                    raise UserError(error_message)
                except UserError:
                    raise
                except:
                    _logger.error(f"WooCommerce 400 Error for coupon {coupon_id}: {response.text}")
                    error_message = self._parse_woocommerce_error_text(response.text)
                    raise UserError(error_message)
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error updating coupon {coupon_id} in WooCommerce: {e}")
            raise UserError(_('Failed to update coupon in WooCommerce: %s') % str(e))
    
    def delete_coupon(self, coupon_id):
        """Delete a coupon from WooCommerce"""
        self.ensure_one()
        
        url = self._get_api_url(f'coupons/{coupon_id}')
        headers = self._get_auth_headers()
        
        try:
            response = requests.delete(url, headers=headers, timeout=600)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error deleting coupon {coupon_id} from WooCommerce: {e}")
            raise UserError(_('Failed to delete coupon from WooCommerce: %s') % str(e))
    
    def action_import_coupons(self):
        """Action to import coupons from WooCommerce"""
        self.ensure_one()
        
        if self.connection_status != 'success':
            raise UserError(_('Please test the connection first before importing coupons.'))
        
        try:
            coupons_data = self.get_coupons(per_page=100)
            
            if not coupons_data:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('No Coupons'),
                        'message': _('No coupons found in WooCommerce'),
                        'type': 'warning',
                    }
                }
            
            Coupon = self.env['woocommerce.coupon']
            created_count = 0
            updated_count = 0
            
            for coupon_data in coupons_data:
                existing = Coupon.search([
                    ('wc_coupon_id', '=', coupon_data['id']),
                    ('connection_id', '=', self.id)
                ], limit=1)
                
                if existing:
                    existing._update_from_woocommerce_data(coupon_data)
                    updated_count += 1
                else:
                    Coupon.create_from_wc_data(coupon_data, self.id)
                    created_count += 1
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Coupons Imported'),
                    'message': _('Created: %d, Updated: %d coupons') % (created_count, updated_count),
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            _logger.error(f"Error importing coupons: {str(e)}")
            raise UserError(_('Failed to import coupons: %s') % str(e))
    
