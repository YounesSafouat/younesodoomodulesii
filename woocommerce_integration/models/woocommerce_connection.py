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
    
    # Import Progress Fields
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
    
    # Background import tracking (persisted on connection record)
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
            
            response = requests.get(url, headers=headers, timeout=600)  # 10 minutes
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
    
    def get_products(self, page=1, per_page=10, **kwargs):
        """Get products from WooCommerce with all attributes included"""
        self.ensure_one()
        
        url = self._get_api_url('products')
        headers = self._get_auth_headers()
        
        params = {
            'page': page,
            'per_page': per_page,
        }
        params.update(kwargs)
        
        # Ensure we get all product data including attributes
        # WooCommerce API parameters to include all data
        include_params = {
            'include_meta': 'true',  # Include meta data
            'include_attributes': 'true',  # Include attributes
            'include_variations': 'true',  # Include variations
            'include_images': 'true',  # Include images
            'include_categories': 'true',  # Include categories
            'include_tags': 'true',  # Include tags
        }
        params.update(include_params)
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=600)  # 10 minutes
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
        
        # Ensure we get all product data including attributes
        params = {
            'include_meta': 'true',  # Include meta data
            'include_attributes': 'true',  # Include attributes
            'include_variations': 'true',  # Include variations
            'include_images': 'true',  # Include images
            'include_categories': 'true',  # Include categories
            'include_tags': 'true',  # Include tags
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=600)  # 10 minutes
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
            response = requests.get(url, headers=headers, timeout=600)  # 10 minutes
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
            response = requests.get(url, headers=headers, params=params, timeout=600)  # 10 minutes
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
            
            # Update parent relationships
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
        
        # Check if mappings already exist
        existing_mappings = self.env['woocommerce.field.mapping'].search([
            ('connection_id', '=', self.id)
        ])
        
        if existing_mappings:
            raise UserError(_('Field mappings already exist for this connection. Please delete existing mappings first if you want to recreate them.'))
        
        # Create default mappings
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
            # Get multiple products to find all custom fields (some products might have different custom fields)
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
            
            # Get global attributes from WooCommerce
            try:
                attributes_data = self.get_attributes(page=1, per_page=100)
            except Exception as e:
                _logger.warning(f"Failed to get attributes: {e}")
                attributes_data = []
            
            # Collect all unique fields from multiple products
            all_fields = set()
            custom_fields = set()
            
            def extract_fields(data, prefix=''):
                """Recursively extract all fields from the product data"""
                fields = []
                for key, value in data.items():
                    if isinstance(value, dict):
                        # For nested objects like dimensions
                        nested_fields = extract_fields(value, f"{prefix}{key}.")
                        fields.extend(nested_fields)
                    elif isinstance(value, list) and value and isinstance(value[0], dict):
                        # For arrays of objects like images, categories, meta_data, attributes
                        if key in ['images', 'categories', 'tags', 'attributes', 'default_attributes', 'variations', 'meta_data']:
                            if key == 'meta_data':
                                # Extract custom fields from meta_data
                                for meta_item in value:
                                    if isinstance(meta_item, dict) and 'key' in meta_item:
                                        meta_key = meta_item.get('key', '')
                                        meta_value = meta_item.get('value', '')
                                        field_name = f"{prefix}meta_data.{meta_key}"
                                        field_label = f"Custom: {meta_key.replace('_', ' ').title()}"
                                        fields.append((field_name, field_label))
                                        # Track custom fields separately
                                        custom_fields.add((field_name, field_label))
                            elif key == 'attributes':
                                # Extract WooCommerce attributes
                                for attr_item in value:
                                    if isinstance(attr_item, dict) and 'name' in attr_item:
                                        attr_name = attr_item.get('name', '')
                                        attr_slug = attr_item.get('slug', '')
                                        attr_id = attr_item.get('id', '')
                                        # Create multiple field variations for attributes
                                        field_name = f"{prefix}attributes.{attr_slug}"
                                        field_label = f"Attribute: {attr_name}"
                                        fields.append((field_name, field_label))
                                        custom_fields.add((field_name, field_label))
                                        
                                        # Also add variations for different ways to access the attribute
                                        field_name_values = f"{prefix}attributes.{attr_slug}.options"
                                        field_label_values = f"Attribute {attr_name} Values"
                                        fields.append((field_name_values, field_label_values))
                                        custom_fields.add((field_name_values, field_label_values))
                            else:
                                fields.append((f"{prefix}{key}", key.replace('_', ' ').title()))
                    else:
                        # For simple fields
                        field_name = f"{prefix}{key}"
                        field_label = key.replace('_', ' ').title()
                        fields.append((field_name, field_label))
                        all_fields.add((field_name, field_label))
                return fields
            
            # Analyze all products to find all fields
            for product in products:
                product_fields = extract_fields(product)
                all_fields.update(product_fields)
            
            # Add global attributes as available fields
            for attr in attributes_data:
                if isinstance(attr, dict):
                    attr_name = attr.get('name', '')
                    attr_slug = attr.get('slug', '')
                    attr_id = attr.get('id', '')
                    
                    if attr_slug:
                        # Add attribute field
                        field_name = f"attributes.{attr_slug}"
                        field_label = f"Attribute: {attr_name}"
                        all_fields.add((field_name, field_label))
                        custom_fields.add((field_name, field_label))
                        
                        # Add attribute values field
                        field_name_values = f"attributes.{attr_slug}.options"
                        field_label_values = f"Attribute {attr_name} Values"
                        all_fields.add((field_name_values, field_label_values))
                        custom_fields.add((field_name_values, field_label_values))
                        
                        # Add attribute by ID
                        field_name_id = f"attributes.{attr_id}"
                        field_label_id = f"Attribute ID {attr_id}: {attr_name}"
                        all_fields.add((field_name_id, field_label_id))
                        custom_fields.add((field_name_id, field_label_id))
            
            # Convert sets back to lists and sort them
            wc_fields = sorted(list(all_fields))
            custom_fields_list = sorted(list(custom_fields))
            
            # Store discovered fields in the connection for use in field mapping
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
            
            # Store the discovered fields in the connection for reference
            attribute_fields = [f for f in wc_fields if f[0].startswith('attributes.')]
            meta_fields = [f for f in wc_fields if f[0].startswith('meta_data.')]
            regular_fields = [f for f in wc_fields if not f[0].startswith(('attributes.', 'meta_data.'))]
            
            field_summary = f'Discovered {len(wc_fields)} WooCommerce fields:\n'
            field_summary += f'  - {len(regular_fields)} regular fields\n'
            field_summary += f'  - {len(attribute_fields)} WooCommerce attributes\n'
            field_summary += f'  - {len(meta_fields)} custom meta fields\n\n'
            
            # Show regular fields
            if regular_fields:
                field_summary += 'Regular Fields:\n'
                field_summary += '\n'.join([f'  {field[0]}: {field[1]}' for field in regular_fields[:10]])
                if len(regular_fields) > 10:
                    field_summary += f'\n  ... and {len(regular_fields) - 10} more regular fields'
                field_summary += '\n\n'
            
            # Show WooCommerce attributes
            if attribute_fields:
                field_summary += 'WooCommerce Attributes:\n'
                field_summary += '\n'.join([f'  {field[0]}: {field[1]}' for field in attribute_fields[:15]])
                if len(attribute_fields) > 15:
                    field_summary += f'\n  ... and {len(attribute_fields) - 15} more attributes'
                field_summary += '\n\n'
            
            # Show custom meta fields
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
        
        # Handle duplicate SKU by making it unique
        if 'sku' in product_data and product_data['sku']:
            original_sku = product_data['sku']
            # Add timestamp to make it unique
            product_data['sku'] = f"{original_sku}-{int(time.time())}"
        
        url = self._get_api_url('products')
        headers = self._get_auth_headers()
        
        try:
            _logger.info(f"Creating WooCommerce product with data: {product_data}")
            response = requests.post(url, headers=headers, json=product_data, timeout=600)  # 10 minutes
            
            if response.status_code == 400:
                try:
                    error_details = response.json()
                    
                    # Handle duplicate SKU error by using the suggested unique SKU
                    if error_details.get('code') == 'product_invalid_sku' and error_details.get('data', {}).get('unique_sku'):
                        suggested_sku = error_details['data']['unique_sku']
                        _logger.info(f"Using WooCommerce suggested unique SKU: {suggested_sku}")
                        product_data['sku'] = suggested_sku
                        
                        # Retry with the suggested SKU
                        retry_response = requests.post(url, headers=headers, json=product_data, timeout=600)  # 10 minutes
                        if retry_response.status_code == 200 or retry_response.status_code == 201:
                            return retry_response.json()
                    
                    _logger.error(f"WooCommerce 400 Error during product creation: {error_details}")
                    raise UserError(_('WooCommerce API Error (400): %s') % str(error_details))
                except:
                    _logger.error(f"WooCommerce 400 Error during product creation: {response.text}")
                    raise UserError(_('WooCommerce API Error (400): %s') % response.text)
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error creating product in WooCommerce: {e}")
            raise UserError(_('Failed to create product in WooCommerce: %s') % str(e))
    
    def update_product(self, product_id, product_data):
        """Update an existing product in WooCommerce"""
        self.ensure_one()
        
        # Always merge with existing data to prevent overwriting other fields
        try:
            current_product = self.get_product(product_id)
            if current_product:
                # Log what we're merging
                _logger.info(f"BEFORE MERGE - Current product has {len(current_product.get('attributes', []))} attributes")
                _logger.info(f"BEFORE MERGE - Update data has {len(product_data.get('attributes', []))} attributes")
                
                # Merge the new data with existing data
                merged_data = current_product.copy()
                merged_data.update(product_data)
                product_data = merged_data
                
                _logger.info(f"AFTER MERGE - Merged data has {len(product_data.get('attributes', []))} attributes")
                _logger.info(f"Merged update with existing data for product {product_id}")
        except Exception as e:
            _logger.warning(f"Failed to get current product data for merge: {e}")
            # Continue with original data if merge fails
        
        url = self._get_api_url(f'products/{product_id}')
        headers = self._get_auth_headers()
        
        try:
            _logger.info(f"Updating WooCommerce product {product_id} with data: {product_data}")
            response = requests.put(url, headers=headers, json=product_data, timeout=600)  # 10 minutes
            
            # Log response details for debugging
            _logger.info(f"WooCommerce API Response - Status: {response.status_code}")
            if response.status_code not in [200, 201]:
                _logger.warning(f"WooCommerce API Response Text: {response.text}")
            
            if response.status_code == 400:
                try:
                    error_details = response.json()
                    _logger.error(f"WooCommerce 400 Error for product {product_id}: {error_details}")
                    raise UserError(_('WooCommerce API Error (400): %s') % str(error_details))
                except:
                    _logger.error(f"WooCommerce 400 Error for product {product_id}: {response.text}")
                    raise UserError(_('WooCommerce API Error (400): %s') % response.text)
            
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
            response = requests.delete(url, headers=headers, timeout=600)  # 10 minutes
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error deleting product {product_id} from WooCommerce: {e}")
            raise UserError(_('Failed to delete product from WooCommerce: %s') % str(e))
    
    def action_create_order_webhook(self):
        """Create order webhook for this connection"""
        self.ensure_one()
        
        # Generate webhook URL
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        webhook_url = f"{base_url}/woocommerce/webhook/{self.id}"
        
        # Create webhook
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
    
