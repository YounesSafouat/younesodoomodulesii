from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    wc_product_id = fields.Integer(
        string='WooCommerce Product ID',
        help='Product ID in WooCommerce'
    )
    
    wc_connection_id = fields.Many2one(
        'woocommerce.connection',
        string='WooCommerce Connection',
        help='WooCommerce connection for this product'
    )
    
    wc_sync_enabled = fields.Boolean(
        string='Sync with WooCommerce',
        default=False,
        help='Enable synchronization with WooCommerce'
    )
    
    wc_last_sync = fields.Datetime(
        string='Last WooCommerce Sync',
        readonly=True,
        help='Last time this product was synchronized with WooCommerce'
    )
    
    wc_sync_status = fields.Selection([
        ('not_synced', 'Not Synced'),
        ('pending', 'Pending'),
        ('synced', 'Synced'),
        ('pending_update', 'Pending Update'),
        ('error', 'Error'),
        ('conflict', 'Sync Conflict'),
    ], string='WooCommerce Sync Status', default='not_synced', readonly=True)
    
    wc_sync_direction = fields.Selection([
        ('odoo_to_wc', 'Odoo → WooCommerce'),
        ('wc_to_odoo', 'WooCommerce → Odoo'),
        ('bidirectional', 'Bidirectional'),
    ], string='Sync Direction', 
       compute='_compute_wc_sync_direction', store=True,
       help='Choose how products should sync between Odoo and WooCommerce')
    
    @api.depends('wc_connection_id', 'wc_connection_id.default_sync_direction')
    def _compute_wc_sync_direction(self):
        """Compute sync direction from connection default"""
        for product in self:
            if product.wc_connection_id and product.wc_connection_id.default_sync_direction:
                product.wc_sync_direction = product.wc_connection_id.default_sync_direction
            else:
                product.wc_sync_direction = 'bidirectional'
    
    wc_auto_sync = fields.Boolean(
        string='Auto Sync on Changes',
        default=True,
        help='Automatically sync when product is updated'
    )
    
    wc_image_sync_enabled = fields.Boolean(
        string='Sync Images',
        default=True,
        help='Include product images in synchronization'
    )
    
    wc_last_error = fields.Text(
        string='Last Sync Error',
        readonly=True,
        help='Details of the last synchronization error'
    )
    
    wc_product_url = fields.Char(
        string='WooCommerce Product URL',
        compute='_compute_wc_product_url',
        help='Direct link to the product in WooCommerce store'
    )
    
    @api.depends('wc_product_id', 'wc_connection_id')
    def _compute_wc_product_url(self):
        """Compute the WooCommerce product URL"""
        for product in self:
            if product.wc_product_id and product.wc_connection_id:
                base_url = product.wc_connection_id.store_url
                if base_url:
                    base_url = base_url.rstrip('/')
                    product.wc_product_url = f"{base_url}/?p={product.wc_product_id}"
                else:
                    product.wc_product_url = False
            else:
                product.wc_product_url = False
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to handle WooCommerce sync"""
        products = super(ProductTemplate, self).create(vals_list)
        
        for product, vals in zip(products, vals_list):
            # If product already has WooCommerce ID (imported from WooCommerce)
            if vals.get('wc_product_id') and vals.get('wc_connection_id'):
                product.wc_sync_status = 'synced'
                product.wc_last_sync = fields.Datetime.now()
            # If sync is enabled and connection is set, auto-create in WooCommerce
            elif vals.get('wc_sync_enabled') and vals.get('wc_connection_id'):
                try:
                    # Create WooCommerce product record first
                    wc_product_vals = {
                        'wc_product_id': 0,  # Will be updated after WooCommerce creation
                        'connection_id': vals['wc_connection_id'],
                        'odoo_product_id': product.id,
                        'name': product.name,
                        'wc_sku': product.default_code or '',
                        'price': product.list_price,
                        'regular_price': product.list_price,
                        'sale_price': 0,
                        'status': 'publish' if product.sale_ok else 'draft',
                        'sync_status': 'pending',
                    }
                    wc_product = self.env['woocommerce.product'].create(wc_product_vals)
                    
                    # Sync to WooCommerce store
                    wc_product._sync_to_woocommerce_store()
                    
                    _logger.info(f"Auto-created product in WooCommerce: {product.name} (ID: {wc_product.wc_product_id})")
                    
                except Exception as e:
                    _logger.error(f"Error auto-creating product in WooCommerce: {e}")
                    product.write({
                        'wc_sync_status': 'error',
                        'wc_last_error': str(e),
                    })
        
        return products
    
    def write(self, vals):
        """Override write to handle WooCommerce sync"""
        sync_fields = ['name', 'list_price', 'default_code', 'description', 'description_sale', 'sale_ok', 'purchase_ok']
        image_fields = ['image_1920', 'image_1024', 'image_512', 'image_256', 'image_128']
        
        result = super(ProductTemplate, self).write(vals)
        
        for product in self:
            if product.wc_sync_enabled and product.wc_connection_id and product.wc_auto_sync:
                should_sync = False
                
                # Check standard fields
                sync_needed = any(key in vals for key in sync_fields)
                if sync_needed:
                    product._update_woocommerce_product_table(vals)
                    should_sync = True
                
                # Check image fields
                image_sync_needed = any(key in vals for key in image_fields)
                if image_sync_needed and product.wc_image_sync_enabled:
                    should_sync = True
                    # Auto-sync images when they change
                    _logger.info(f"Image changed for product {product.name}, triggering auto-sync")
                
                # Check custom mapped fields (from field mappings)
                if product.wc_connection_id:
                    mapped_fields = product._get_mapped_odoo_fields()
                    if any(key in vals for key in mapped_fields):
                        _logger.info(f"Custom mapped field changed: {[k for k in vals.keys() if k in mapped_fields]}")
                        should_sync = True
                
                if should_sync:
                    # Update status without triggering another write cycle
                    self.env.cr.execute("""
                        UPDATE product_template 
                        SET wc_sync_status = 'pending_update',
                            wc_last_sync = %s
                        WHERE id = %s
                    """, (fields.Datetime.now(), product.id))
                    
                    # Pass updated fields context for partial sync
                    updated_fields = [key for key in vals.keys() if key in sync_fields + mapped_fields]
                    product.with_context(updated_fields=updated_fields)._queue_woocommerce_sync()
        
        return result
    
    def _get_mapped_odoo_fields(self):
        """Get list of Odoo fields that are mapped in field mappings"""
        self.ensure_one()
        
        if not self.wc_connection_id:
            return []
        
        # Get all active field mappings for this connection (Odoo to WooCommerce direction)
        mappings = self.env['woocommerce.field.mapping'].search([
            ('connection_id', '=', self.wc_connection_id.id),
            ('is_active', '=', True),
            ('mapping_direction', 'in', ['odoo_to_wc', 'bidirectional']),
        ])
        
        # Extract Odoo field names
        field_names = [m.odoo_field_name for m in mappings if m.odoo_field_name]
        
        return field_names
    
    def _queue_woocommerce_sync(self):
        """Queue product for WooCommerce synchronization"""
        self.ensure_one()
        
        if self.env.context.get('skip_wc_sync') or self.env.context.get('importing_from_woocommerce'):
            return
        
        try:
            self._sync_to_woocommerce()
        except Exception as e:
            self.write({
                'wc_sync_status': 'error',
                'wc_last_error': str(e),
            })
    
    def _sync_to_woocommerce(self):
        """Internal method to sync product to WooCommerce"""
        self.ensure_one()
        
        if not self.wc_connection_id:
            raise ValidationError(_('No WooCommerce connection configured.'))
        
        try:
            # Check if this is a partial sync (triggered from WooCommerce product)
            updated_fields = self.env.context.get('updated_fields', [])
            
            if updated_fields and self.wc_product_id:
                # Use partial sync through WooCommerce product
                wc_product = self.env['woocommerce.product'].search([
                    ('wc_product_id', '=', self.wc_product_id),
                    ('connection_id', '=', self.wc_connection_id.id)
                ])
                if wc_product:
                    wc_product.with_context(updated_fields=updated_fields)._sync_to_woocommerce_store()
                    return
            
            # Full sync (manual or initial sync)
            product_data = self._prepare_woocommerce_data()
            
            if self.wc_product_id:
                response = self.wc_connection_id.update_product(self.wc_product_id, product_data)
                if response:
                    _logger.info(f"Updated WooCommerce product {self.wc_product_id}: {self.name}")
                else:
                    raise Exception("Failed to update product in WooCommerce")
            else:
                response = self.wc_connection_id.create_product(product_data)
                if response and response.get('id'):
                    self.write({
                        'wc_product_id': response['id'],
                        'wc_sync_status': 'synced',
                        'wc_last_error': False,
                        'wc_last_sync': fields.Datetime.now(),
                    })
                    _logger.info(f"Created WooCommerce product {response['id']}: {self.name}")
                else:
                    raise Exception("Failed to create product in WooCommerce")
            
            self.write({
                'wc_sync_status': 'synced',
                'wc_last_error': False,
                'wc_last_sync': fields.Datetime.now(),
            })
            
        except Exception as e:
            error_msg = f"WooCommerce sync failed: {str(e)}"
            _logger.error(f"Error syncing product {self.name} to WooCommerce: {e}")
            self.write({
                'wc_sync_status': 'error',
                'wc_last_error': error_msg,
            })
            raise Exception(error_msg)
    
    def _prepare_woocommerce_data(self):
        """Prepare product data for WooCommerce API using WooCommerce product table data"""
        self.ensure_one()
        
        wc_product = self.env['woocommerce.product'].search([
            ('wc_product_id', '=', self.wc_product_id),
            ('connection_id', '=', self.wc_connection_id.id)
        ])
        
        # Check if stock is mapped, if not, don't include it
        stock_quantity = None
        if self.wc_connection_id:
            # Check if there's a mapping for stock quantity
            stock_mappings = self.env['woocommerce.field.mapping'].search([
                ('connection_id', '=', self.wc_connection_id.id),
                ('is_active', '=', True),
                ('mapping_direction', 'in', ['odoo_to_wc', 'bidirectional']),
                ('wc_field_name', 'ilike', 'stock')
            ])
            
            if stock_mappings:
                # Use mapped field value
                for mapping in stock_mappings:
                    if mapping.odoo_field_name:
                        try:
                            stock_value = getattr(self, mapping.odoo_field_name, 0)
                            if stock_value is not None:
                                stock_quantity = int(stock_value) if stock_value else 0
                                break
                        except (ValueError, TypeError, AttributeError):
                            continue
            
            # If no mapping found, don't send stock data at all
            # This prevents overwriting WooCommerce stock settings
        
        if wc_product:
            regular_price = str(float(wc_product.regular_price)) if wc_product.regular_price else '0.00'
            sale_price = str(float(wc_product.sale_price)) if wc_product.sale_price else ''
            
            if wc_product.sale_price and wc_product.sale_price > 0:
                current_price = sale_price
            else:
                current_price = regular_price
        else:
            regular_price = '0.00'
            sale_price = str(float(self.list_price)) if self.list_price else '0.00'
            current_price = sale_price
        
        data = {
            'name': self.name or 'Untitled Product',
            'type': 'simple',
            'regular_price': regular_price,
            'description': self.description or '',
            'short_description': self.description_sale or '',
            'status': 'publish' if self.sale_ok else 'draft',
            'sku': self.default_code or '',
            'weight': '',
            'dimensions': {
                'length': '',
                'width': '',
                'height': ''
            },
            'tax_status': 'taxable',
            'tax_class': '',
            'catalog_visibility': 'visible',
            'featured': False,
            'virtual': False,
            'downloadable': False,
        }
        
        # Only include stock if it's mapped
        if stock_quantity is not None:
            data['manage_stock'] = True
            data['stock_quantity'] = stock_quantity
            _logger.info(f"Including stock data: manage_stock=True, stock_quantity={stock_quantity}")
        else:
            _logger.info("No stock mapping found - preserving WooCommerce stock settings")
        
        if sale_price and float(sale_price) > 0:
            data['sale_price'] = sale_price
        
        # Handle image sync
        _logger.info(f"Image sync check - wc_image_sync_enabled: {self.wc_image_sync_enabled}, has image_1920: {bool(self.image_1920)}")
        
        images_to_sync = []
        
        # Check main product image
        if self.wc_image_sync_enabled and self.image_1920:
            _logger.info(f"Processing main product image for {self.name}")
            
            # Use the configured image upload method
            if self.wc_connection_id.image_upload_method == 'wordpress_media':
                # For WordPress Media Library, we need to upload the image first
                # This should be done through the WooCommerce product image system
                _logger.info(f"WordPress Media Library method requires individual image sync first")
            else:  # woocommerce_base64
                image_data = self._process_product_image()
                if image_data:
                    images_to_sync.append({
                        'src': image_data,
                        'name': self.name or 'Product Image',
                        'alt': self.name or ''
                    })
                    _logger.info(f"Added main product image to WooCommerce data for product {self.name}")
                else:
                    _logger.warning(f"Failed to process main product image for product {self.name}")
        
        # Check WooCommerce product images
        if self.wc_image_sync_enabled:
            wc_product = self.env['woocommerce.product'].search([
                ('odoo_product_id', '=', self.id),
                ('connection_id', '=', self.wc_connection_id.id)
            ], limit=1)
            
            if wc_product and wc_product.product_image_ids:
                _logger.info(f"Found {len(wc_product.product_image_ids)} WooCommerce product images for {self.name}")
                for wc_image in wc_product.product_image_ids:
                    # Use the configured image upload method
                    if self.wc_connection_id.image_upload_method == 'wordpress_media':
                        # WordPress Media Library approach - use Media ID
                        if wc_image.sync_status == 'synced' and wc_image.wc_image_id and wc_image.wc_image_url:
                            _logger.info(f"Using WordPress Media Library image: {wc_image.name} (ID: {wc_image.wc_image_id})")
                            images_to_sync.append({
                                'id': wc_image.wc_image_id,
                                'src': wc_image.wc_image_url,
                                'name': wc_image.name or 'Product Image',
                                'alt': wc_image.alt_text or wc_image.name or ''
                            })
                            _logger.info(f"Added WordPress Media Library image to sync data: {wc_image.name}")
                        elif wc_image.image_1920 and wc_image.sync_status != 'synced':
                            _logger.info(f"Image {wc_image.name} needs to be synced to WordPress Media Library first")
                    else:  # woocommerce_base64
                        # Base64 approach - process image directly
                        if wc_image.image_1920:
                            _logger.info(f"Processing WooCommerce product image: {wc_image.name}")
                            image_data = self._process_woocommerce_product_image(wc_image)
                            if image_data:
                                images_to_sync.append({
                                    'src': image_data,
                                    'name': wc_image.name or 'Product Image',
                                    'alt': wc_image.alt_text or wc_image.name or ''
                                })
                                _logger.info(f"Added WooCommerce product image to sync data: {wc_image.name}")
                            else:
                                _logger.warning(f"Failed to process WooCommerce product image: {wc_image.name}")
        
        if images_to_sync:
            data['images'] = images_to_sync
            _logger.info(f"Total images to sync for product {self.name}: {len(images_to_sync)}")
        else:
            _logger.info(f"No images to sync - wc_image_sync_enabled: {self.wc_image_sync_enabled}, main image: {bool(self.image_1920)}")
        
        # Handle custom attributes from field mappings
        custom_attributes = self._prepare_custom_attributes()
        
        # Always include existing attributes from WooCommerce to prevent data loss
        existing_attributes = self._get_existing_woocommerce_attributes()
        if existing_attributes:
            # Merge custom attributes with existing ones
            if custom_attributes:
                # Create a map of existing attributes by slug
                existing_attr_map = {attr.get('slug', attr.get('name', '')): attr for attr in existing_attributes}
                
                # Update existing attributes with new values from custom attributes
                for custom_attr in custom_attributes:
                    attr_slug = custom_attr.get('name', '')
                    if attr_slug in existing_attr_map:
                        # Update existing attribute with new value
                        existing_attr_map[attr_slug].update(custom_attr)
                    else:
                        # Add new attribute
                        existing_attributes.append(custom_attr)
                
                data['attributes'] = existing_attributes
            else:
                # No custom attributes, just use existing ones
                data['attributes'] = existing_attributes
        elif custom_attributes:
            # No existing attributes, just use custom ones
            data['attributes'] = custom_attributes
        
        return data
    
    def _get_existing_woocommerce_attributes(self):
        """Get existing attributes from WooCommerce to preserve them during updates"""
        self.ensure_one()
        
        if not self.wc_product_id or not self.wc_connection_id:
            return []
        
        try:
            # Get current product data from WooCommerce
            current_product = self.wc_connection_id.get_product(self.wc_product_id)
            if current_product and current_product.get('attributes'):
                _logger.info(f"Retrieved {len(current_product['attributes'])} existing attributes from WooCommerce")
                return current_product['attributes']
        except Exception as e:
            _logger.warning(f"Failed to get existing WooCommerce attributes: {e}")
        
        return []
    
    def _prepare_custom_attributes(self):
        """Prepare custom attributes from field mappings for WooCommerce"""
        self.ensure_one()
        
        if not self.wc_connection_id:
            return []
        
        # Get field mappings for Odoo to WooCommerce
        mappings = self.env['woocommerce.field.mapping'].search([
            ('connection_id', '=', self.wc_connection_id.id),
            ('is_active', '=', True),
            ('mapping_direction', 'in', ['odoo_to_wc', 'bidirectional']),
        ])
        
        attributes = []
        
        for mapping in mappings:
            # Skip standard fields (already handled above)
            if mapping.odoo_field_name in ['name', 'list_price', 'default_code', 'description', 'description_sale']:
                continue
            
            # Only process WooCommerce attributes (starting with 'attributes.')
            if not mapping.wc_field_name or not mapping.wc_field_name.startswith('attributes.'):
                continue
            
            try:
                # Get the value from Odoo
                odoo_value = getattr(self, mapping.odoo_field_name, None)
                
                if odoo_value is None or odoo_value == False:
                    continue
                
                # Convert value to string
                if isinstance(odoo_value, (int, float)):
                    odoo_value = str(odoo_value)
                elif hasattr(odoo_value, 'name'):  # Many2one field
                    odoo_value = odoo_value.name
                
                # Apply reverse transformation if needed
                # (Note: We're sending from Odoo to WC, so we might need to reverse some transformations)
                final_value = str(odoo_value)
                
                # Extract attribute slug from wc_field_name (e.g., 'attributes.pa_choix-de-bois' -> 'pa_choix-de-bois')
                wc_field_parts = mapping.wc_field_name.split('.')
                if len(wc_field_parts) >= 2:
                    attr_slug = wc_field_parts[1].replace('.options', '')
                    
                    # Ensure attribute exists in WooCommerce first
                    self._ensure_woocommerce_attribute_exists(attr_slug, final_value)
                    
                    # Format for WooCommerce API - try different formats
                    attributes.append({
                        'name': attr_slug,
                        'options': [final_value],  # WooCommerce expects options as array
                        'visible': True,
                        'variation': False
                    })
                    
                    _logger.info(f"Prepared attribute {attr_slug} = {final_value} for WooCommerce")
                    
            except Exception as e:
                _logger.error(f"Error preparing attribute {mapping.name}: {e}")
                continue
        
        return attributes
    
    def _ensure_woocommerce_attribute_exists(self, attr_slug, option_value):
        """Ensure that a WooCommerce attribute exists before using it on a product"""
        self.ensure_one()
        
        if not self.wc_connection_id:
            return
        
        try:
            # Check if attribute exists
            import requests
            
            url = f"{self.wc_connection_id.store_url}/wp-json/wc/v3/products/attributes"
            headers = self.wc_connection_id._get_auth_headers()
            
            # Search for existing attribute
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                attributes = response.json()
                existing_attr = None
                
                for attr in attributes:
                    if attr.get('slug') == attr_slug:
                        existing_attr = attr
                        break
                
                if existing_attr:
                    # Attribute exists, check if option exists
                    attr_id = existing_attr['id']
                    terms_url = f"{url}/{attr_id}/terms"
                    terms_response = requests.get(terms_url, headers=headers, timeout=30)
                    
                    if terms_response.status_code == 200:
                        terms = terms_response.json()
                        existing_term = any(term.get('name', '').lower() == option_value.lower() for term in terms)
                        
                        if not existing_term:
                            # Create the term
                            term_data = {'name': option_value}
                            requests.post(terms_url, headers=headers, json=term_data, timeout=30)
                            _logger.info(f"Created WooCommerce attribute term: {option_value} for {attr_slug}")
                else:
                    # Create the attribute
                    attr_data = {
                        'name': attr_slug.replace('pa_', '').replace('-', ' ').title(),
                        'slug': attr_slug,
                        'type': 'select',
                        'order_by': 'menu_order',
                        'has_archives': False
                    }
                    
                    create_response = requests.post(url, headers=headers, json=attr_data, timeout=30)
                    
                    if create_response.status_code == 201:
                        new_attr = create_response.json()
                        attr_id = new_attr['id']
                        
                        # Create the term
                        terms_url = f"{url}/{attr_id}/terms"
                        term_data = {'name': option_value}
                        requests.post(terms_url, headers=headers, json=term_data, timeout=30)
                        
                        _logger.info(f"Created WooCommerce attribute: {attr_slug} with term: {option_value}")
                        
        except Exception as e:
            _logger.error(f"Error ensuring WooCommerce attribute exists: {e}")
    
    def _update_woocommerce_product_table(self, vals):
        """Update the WooCommerce product table with new data from Odoo"""
        self.ensure_one()
        
        if not self.wc_product_id or not self.wc_connection_id:
            return
        
        wc_product = self.env['woocommerce.product'].search([
            ('wc_product_id', '=', self.wc_product_id),
            ('connection_id', '=', self.wc_connection_id.id)
        ])
        
        if not wc_product:
            return
        
        wc_update_vals = {}
        
        if 'name' in vals:
            wc_update_vals['name'] = vals['name']
        
        if 'list_price' in vals:
            wc_update_vals['sale_price'] = float(vals['list_price'])
            
            if wc_product.regular_price and wc_product.regular_price > 0:
                wc_update_vals['price'] = float(vals['list_price'])
            else:
                wc_update_vals['regular_price'] = float(vals['list_price'])
                wc_update_vals['price'] = float(vals['list_price'])
        
        if 'default_code' in vals:
            wc_update_vals['wc_sku'] = vals['default_code']
        
        if 'description' in vals:
            wc_update_vals['wc_data'] = str(self._get_updated_wc_data(vals))
        
        if 'description_sale' in vals:
            wc_update_vals['wc_data'] = str(self._get_updated_wc_data(vals))
        
        if 'sale_ok' in vals:
            wc_update_vals['status'] = 'publish' if vals['sale_ok'] else 'draft'
        
        if wc_update_vals:
            wc_update_vals['last_sync'] = fields.Datetime.now()
            wc_update_vals['sync_status'] = 'pending'
            
            # Pass the updated fields in context for partial sync
            updated_fields = list(wc_update_vals.keys())
            _logger.info(f"Product template updating WooCommerce product with fields: {updated_fields}")
            wc_product = wc_product.with_context(updated_fields=updated_fields)
            wc_product.write(wc_update_vals)
            
            _logger.info(f"Updated WooCommerce product table for {self.name}: {wc_update_vals}")
    
    def _get_updated_wc_data(self, vals):
        """Get updated WooCommerce data with new values"""
        self.ensure_one()
        
        wc_product = self.env['woocommerce.product'].search([
            ('wc_product_id', '=', self.wc_product_id),
            ('connection_id', '=', self.wc_connection_id.id)
        ])
        
        if wc_product and wc_product.wc_data:
            try:
                import json
                wc_data = json.loads(wc_product.wc_data)
            except:
                wc_data = {}
        else:
            wc_data = {}
        
        if 'description' in vals:
            wc_data['description'] = vals['description']
        if 'description_sale' in vals:
            wc_data['short_description'] = vals['description_sale']
        if 'name' in vals:
            wc_data['name'] = vals['name']
        if 'default_code' in vals:
            wc_data['sku'] = vals['default_code']
        
        return wc_data
    
    def _process_product_image(self):
        """Process and upload product image to WooCommerce"""
        self.ensure_one()
        
        if not self.image_1920:
            return None
        
        try:
            import base64
            import io
            
            # Try to import PIL
            try:
                from PIL import Image
            except ImportError:
                _logger.error("PIL (Pillow) is not installed. Cannot process images for WooCommerce.")
                return None
            
            image_data = base64.b64decode(self.image_1920)
            image = Image.open(io.BytesIO(image_data))
            
            _logger.info(f"Original image size: {image.size} for product {self.name}")
            
            if image.size[0] > 800 or image.size[1] > 800:
                image.thumbnail((800, 800), Image.Resampling.LANCZOS)
                _logger.info(f"Resized image to: {image.size} for product {self.name}")
            
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=85)
            processed_data = base64.b64encode(buffer.getvalue()).decode()
            
            _logger.info(f"Successfully processed image for product {self.name}, size: {len(processed_data)} chars")
            return f"data:image/jpeg;base64,{processed_data}"
            
        except Exception as e:
            _logger.error(f"Failed to process image for product {self.name}: {str(e)}")
            self.env['ir.logging'].sudo().create({
                'name': 'WooCommerce Image Processing',
                'level': 'WARNING',
                'message': f'Failed to process image for product {self.name}: {str(e)}',
                'path': 'woocommerce_integration',
                'line': 1,
                'func': '_process_product_image',
            })
            return None
    
    def _process_woocommerce_product_image(self, wc_image):
        """Process and upload WooCommerce product image to WooCommerce"""
        if not wc_image.image_1920:
            return None
        
        try:
            import base64
            import io
            
            # Try to import PIL
            try:
                from PIL import Image
            except ImportError:
                _logger.error("PIL (Pillow) is not installed. Cannot process images for WooCommerce.")
                return None
            
            image_data = base64.b64decode(wc_image.image_1920)
            image = Image.open(io.BytesIO(image_data))
            
            _logger.info(f"Original WooCommerce image size: {image.size} for {wc_image.name}")
            
            if image.size[0] > 800 or image.size[1] > 800:
                image.thumbnail((800, 800), Image.Resampling.LANCZOS)
                _logger.info(f"Resized WooCommerce image to: {image.size} for {wc_image.name}")
            
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=85)
            processed_data = base64.b64encode(buffer.getvalue()).decode()
            
            _logger.info(f"Successfully processed WooCommerce image for {wc_image.name}, size: {len(processed_data)} chars")
            return f"data:image/jpeg;base64,{processed_data}"
            
        except Exception as e:
            _logger.error(f"Failed to process WooCommerce image for {wc_image.name}: {str(e)}")
            return None
    
    def _get_or_create_wc_category_id(self):
        """Get or create WooCommerce category ID for Odoo category"""
        self.ensure_one()
        return 1
    
    def action_sync_to_woocommerce(self):
        """Manual sync product to WooCommerce"""
        self.ensure_one()
        
        if not self.wc_connection_id or not self.wc_sync_enabled:
            raise ValidationError(_('Please enable WooCommerce sync and select a connection.'))
        
        try:
            self._sync_to_woocommerce()
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Successful'),
                    'message': _('Product synchronized to WooCommerce successfully.'),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Failed'),
                    'message': _('Failed to sync product to WooCommerce: %s') % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
    
    def action_view_woocommerce_product(self):
        """View corresponding WooCommerce product"""
        self.ensure_one()
        
        if not self.wc_product_id or not self.wc_connection_id:
            raise ValidationError(_('This product is not linked to a WooCommerce product.'))
        
        wc_product = self.env['woocommerce.product'].search([
            ('wc_product_id', '=', self.wc_product_id),
            ('connection_id', '=', self.wc_connection_id.id)
        ])
        
        if not wc_product:
            raise ValidationError(_('WooCommerce product record not found.'))
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'woocommerce.product',
            'res_id': wc_product.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_batch_sync_to_woocommerce(self):
        """Batch sync multiple products to WooCommerce"""
        products = self.filtered(lambda p: p.wc_sync_enabled and p.wc_connection_id)
        
        if not products:
            raise ValidationError(_('No products selected for synchronization.'))
        
        success_count = 0
        error_count = 0
        error_messages = []
        
        for product in products:
            try:
                product._sync_to_woocommerce()
                success_count += 1
            except Exception as e:
                error_count += 1
                error_messages.append(f"{product.name}: {str(e)}")
                product.write({
                    'wc_sync_status': 'error',
                    'wc_last_error': str(e),
                })
        
        if error_count == 0:
            message = _('Successfully synchronized %d products to WooCommerce.') % success_count
            message_type = 'success'
        else:
            message = _('Synchronized %d products successfully, %d failed.') % (success_count, error_count)
            message_type = 'warning'
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Batch Sync Complete'),
                'message': message,
                'type': message_type,
                'sticky': error_count > 0,
                'details': '\n'.join(error_messages) if error_messages else None,
            }
        }
    
    def action_resolve_sync_conflicts(self):
        """Show wizard to resolve sync conflicts"""
        conflicts = self.filtered(lambda p: p.wc_sync_status == 'conflict')
        
        if not conflicts:
            raise ValidationError(_('No sync conflicts found for selected products.'))
        
        wizard = self.env['woocommerce.conflict.resolution.wizard'].create({
            'product_ids': [(6, 0, conflicts.ids)],
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'woocommerce.conflict.resolution.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'name': _('Resolve Sync Conflicts'),
        }
    
    def action_view_woocommerce_images(self):
        """View WooCommerce product images"""
        self.ensure_one()
        
        if not self.wc_product_id or not self.wc_connection_id:
            raise ValidationError(_('This product is not linked to a WooCommerce product.'))
        
        wc_product = self.env['woocommerce.product'].search([
            ('wc_product_id', '=', self.wc_product_id),
            ('connection_id', '=', self.wc_connection_id.id)
        ])
        
        if not wc_product:
            raise ValidationError(_('WooCommerce product record not found.'))
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('WooCommerce Images - %s') % self.name,
            'res_model': 'woocommerce.product.image',
            'view_mode': 'list,form',
            'domain': [('product_id', '=', wc_product.id)],
            'context': {
                'default_product_id': wc_product.id,
                'default_name': self.name,
            },
            'target': 'current',
        }