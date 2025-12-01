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
            if product.wc_connection_id:
                if product.wc_connection_id.default_sync_direction:
                    product.wc_sync_direction = product.wc_connection_id.default_sync_direction
                else:
                    product.wc_sync_direction = 'bidirectional'  # Default if connection has no default
            else:
                # If no connection, keep existing direction or default to bidirectional
                if not product.wc_sync_direction:
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
    
    wc_sale_price = fields.Float(
        string='WooCommerce Sale Price',
        compute='_compute_wc_sale_price',
        readonly=True,
        help='Sale price in WooCommerce (calculated from active promotions). If no promotion is active, it equals the regular price.'
    )
    
    wc_manual_sale_price = fields.Float(
        string='Manual Sale Price',
        help='Manually set sale price for WooCommerce. When set, this will override any active promotions and disable them for this product. Leave empty to use automatic promotion pricing.'
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
    
    @api.depends('wc_product_id', 'wc_connection_id')
    def _compute_wc_sale_price(self):
        """Compute the WooCommerce sale price from the linked woocommerce.product"""
        for product in self:
            if product.wc_product_id and product.wc_connection_id:
                wc_product = self.env['woocommerce.product'].search([
                    ('wc_product_id', '=', product.wc_product_id),
                    ('connection_id', '=', product.wc_connection_id.id)
                ], limit=1)
                if wc_product:
                    product.wc_sale_price = wc_product.sale_price if wc_product.sale_price else (wc_product.regular_price if wc_product.regular_price else product.list_price)
                else:
                    product.wc_sale_price = product.list_price  # Default to list_price if no WooCommerce product found
            else:
                product.wc_sale_price = product.list_price  # Default to list_price if not linked to WooCommerce
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to handle WooCommerce sync"""
        # Auto-enable sync and set sync direction when connection is set during create
        for vals in vals_list:
            if vals.get('wc_connection_id'):
                # Auto-enable sync if not explicitly set
                if 'wc_sync_enabled' not in vals:
                    vals['wc_sync_enabled'] = True
                
                # Set sync direction from connection if not explicitly set
                if 'wc_sync_direction' not in vals:
                    connection = self.env['woocommerce.connection'].browse(vals['wc_connection_id'])
                    if connection and connection.default_sync_direction:
                        vals['wc_sync_direction'] = connection.default_sync_direction
                    else:
                        vals['wc_sync_direction'] = 'bidirectional'  # Default fallback
        
        products = super(ProductTemplate, self).create(vals_list)
        
        for product, vals in zip(products, vals_list):

            if vals.get('wc_product_id') and vals.get('wc_connection_id'):
                product.wc_sync_status = 'synced'
                product.wc_last_sync = fields.Datetime.now()

            elif vals.get('wc_sync_enabled') and vals.get('wc_connection_id'):
                try:

                    wc_product_vals = {
                        'wc_product_id': 0,
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
                    

                    wc_product._sync_to_woocommerce_store()
                    
                    _logger.info(f"Auto-created product in WooCommerce: {product.name} (ID: {wc_product.wc_product_id})")
                    
                except Exception as e:
                    _logger.error(f"Error auto-creating product in WooCommerce: {e}")
                    product.write({
                        'wc_sync_status': 'error',
                        'wc_last_error': str(e),
                    })
        
        return products
    
    def _disable_promotions_for_product(self, product, manual_sale_price):
        """Disable active promotions for a product when manual sale price is set"""
        if not product.wc_connection_id:
            return self.env['woocommerce.promotion']
        
        # Find active promotions that include this product
        now = fields.Datetime.now()
        active_promotions = self.env['woocommerce.promotion'].search([
            ('connection_id', '=', product.wc_connection_id.id),
            ('active', '=', True),
            ('status', 'in', ['active', 'scheduled']),
        ])
        
        promotions_to_disable = self.env['woocommerce.promotion']
        
        for promotion in active_promotions:
            # Check if product is directly in promotion
            if product.id in promotion.product_ids.ids:
                promotions_to_disable |= promotion
            # Check if product category is in promotion
            elif promotion.product_category_ids and product.categ_id.id in promotion.product_category_ids.ids:
                promotions_to_disable |= promotion
        
        # Disable the promotions
        if promotions_to_disable:
            promotions_to_disable.write({'active': False})
            _logger.info(f"Disabled {len(promotions_to_disable)} promotion(s) for product {product.name} due to manual sale price")
        
        return promotions_to_disable
    
    def _update_woocommerce_sale_price(self, sale_price):
        """Update WooCommerce sale price directly"""
        self.ensure_one()
        
        if not self.wc_product_id or not self.wc_connection_id:
            return
        
        wc_product = self.env['woocommerce.product'].search([
            ('wc_product_id', '=', self.wc_product_id),
            ('connection_id', '=', self.wc_connection_id.id)
        ], limit=1)
        
        if wc_product:
            # Update sale price and sync to WooCommerce
            wc_product.with_context(
                skip_promotion_recalculation=True,
                manual_sale_price_update=True
            ).write({'sale_price': sale_price})
            
            # Sync to WooCommerce store
            try:
                wc_product._sync_to_woocommerce_store()
                _logger.info(f"Updated WooCommerce sale price to {sale_price} for product {self.name}")
            except Exception as e:
                _logger.error(f"Error syncing sale price to WooCommerce for product {self.name}: {e}")
                raise
    
    def _clear_manual_sale_price(self):
        """Clear manual sale price and recalculate from promotions"""
        self.ensure_one()
        
        if not self.wc_product_id or not self.wc_connection_id:
            return
        
        wc_product = self.env['woocommerce.product'].search([
            ('wc_product_id', '=', self.wc_product_id),
            ('connection_id', '=', self.wc_connection_id.id)
        ], limit=1)
        
        if wc_product:
            # Recalculate sale price from promotions
            wc_product._recalculate_sale_price_from_promotions()
            
            # Sync to WooCommerce store
            try:
                wc_product._sync_to_woocommerce_store()
                _logger.info(f"Cleared manual sale price and recalculated from promotions for product {self.name}")
            except Exception as e:
                _logger.error(f"Error syncing after clearing manual sale price for product {self.name}: {e}")
    
    def write(self, vals):
        """Override write to handle WooCommerce sync"""
        sync_fields = ['name', 'list_price', 'default_code', 'description', 'description_sale', 'sale_ok', 'purchase_ok']
        image_fields = ['image_1920', 'image_1024', 'image_512', 'image_256', 'image_128']
        
        # Protect wc_connection_id from being changed if product is already synced
        if 'wc_connection_id' in vals:
            for product in self:
                if product.wc_connection_id and product.wc_connection_id.id != vals.get('wc_connection_id'):
                    if product.wc_product_id or product.wc_sync_status in ['synced', 'pending_update']:
                        raise UserError(_('Cannot change WooCommerce connection. This product is already linked to a WooCommerce store. Changing the connection could break synchronization. Please unlink the product first if you need to change the connection.'))
        
        # Handle manual sale price update - disable promotions and sync to WooCommerce
        manual_sale_price_updated = False
        disabled_promotions_list = []
        manual_sale_price_value = None
        
        if 'wc_manual_sale_price' in vals:
            manual_sale_price = vals.get('wc_manual_sale_price')
            manual_sale_price_value = manual_sale_price
            for product in self:
                if product.wc_sync_enabled and product.wc_connection_id and product.wc_product_id:
                    # Find and disable active promotions for this product
                    disabled_promotions = self._disable_promotions_for_product(product, manual_sale_price)
                    if disabled_promotions:
                        disabled_promotions_list.extend(disabled_promotions)
                    
                    # Update WooCommerce sale price
                    if manual_sale_price and manual_sale_price > 0:
                        product._update_woocommerce_sale_price(manual_sale_price)
                        manual_sale_price_updated = True
                    elif not manual_sale_price or manual_sale_price == 0:
                        # Clear manual sale price - recalculate from promotions
                        product._clear_manual_sale_price()
                        manual_sale_price_updated = True
        
        # Auto-enable sync when connection is set (if not already enabled and not explicitly set to False)
        if 'wc_connection_id' in vals and vals.get('wc_connection_id') and 'wc_sync_enabled' not in vals:
            # Enable sync for products that don't have it enabled yet
            # We'll update them individually after the write
            products_to_enable_sync = []
        
        result = super(ProductTemplate, self).write(vals)
        
        # After write, enable sync and set sync direction for products that got a connection
        if 'wc_connection_id' in vals and vals.get('wc_connection_id'):
            connection = self.env['woocommerce.connection'].browse(vals['wc_connection_id'])
            products_to_update = self.filtered(lambda p: p.wc_connection_id)
            
            if connection:
                update_vals = {}
                
                # Auto-enable sync if not already enabled (unless explicitly set to False)
                if 'wc_sync_enabled' not in vals:
                    products_to_enable = products_to_update.filtered(lambda p: not p.wc_sync_enabled)
                    if products_to_enable:
                        update_vals['wc_sync_enabled'] = True
                
                # Set sync direction from connection's default_sync_direction
                # The compute method should handle this, but we'll set it explicitly to ensure it's correct
                if connection.default_sync_direction:
                    # Check which products need their direction updated
                    products_needing_direction = products_to_update.filtered(
                        lambda p: not p.wc_sync_direction or p.wc_sync_direction != connection.default_sync_direction
                    )
                    if products_needing_direction:
                        update_vals['wc_sync_direction'] = connection.default_sync_direction
                
                if update_vals:
                    products_to_update.write(update_vals)
                    _logger.info(f"Auto-enabled WooCommerce sync and set direction to '{connection.default_sync_direction}' for {len(products_to_update)} product(s) from connection {connection.name}")
        
        for product in self:
            if product.wc_sync_enabled and product.wc_connection_id and product.wc_auto_sync:
                # Check sync direction - only sync to WooCommerce if bidirectional or odoo_to_wc
                sync_direction = product.wc_sync_direction
                if sync_direction not in ['bidirectional', 'odoo_to_wc']:
                    _logger.debug(f"Skipping sync to WooCommerce for {product.name} - sync_direction is {sync_direction}")
                    continue
                
                should_sync = False
                mapped_fields = []
                

                sync_needed = any(key in vals for key in sync_fields)
                if sync_needed:
                    product._update_woocommerce_product_table(vals)
                    should_sync = True
                

                image_sync_needed = any(key in vals for key in image_fields)
                if image_sync_needed and product.wc_image_sync_enabled:
                    should_sync = True

                    _logger.info(f"Image changed for product {product.name}, triggering auto-sync")

                    if 'image_1920' in vals and product.wc_product_id and product.wc_connection_id:
                        self._process_product_image_for_sync(product)
                

                if product.wc_connection_id:
                    mapped_fields = product._get_mapped_odoo_fields()
                    if any(key in vals for key in mapped_fields):
                        _logger.info(f"Custom mapped field changed: {[k for k in vals.keys() if k in mapped_fields]}")
                        should_sync = True
                
                if should_sync:

                    self.env.cr.execute("""
                        UPDATE product_template 
                        SET wc_sync_status = 'pending_update',
                            wc_last_sync = %s
                        WHERE id = %s
                    """, (fields.Datetime.now(), product.id))
                    

                    updated_fields = [key for key in vals.keys() if key in sync_fields + mapped_fields]
                    product.with_context(updated_fields=updated_fields)._queue_woocommerce_sync()
        
        # Show notification for manual sale price update
        if manual_sale_price_updated and manual_sale_price_value and manual_sale_price_value > 0:
            # Get unique promotions
            unique_promotions = list(set(disabled_promotions_list))
            promotion_names = ', '.join([p.name for p in unique_promotions[:5]])  # Limit to first 5
            if len(unique_promotions) > 5:
                promotion_names += _(' and %d more') % (len(unique_promotions) - 5)
            
            message = _('Manual sale price set to %s.') % manual_sale_price_value
            if unique_promotions:
                message += _(' %d promotion(s) disabled: %s') % (len(unique_promotions), promotion_names)
            else:
                message += _(' No active promotions found for this product.')
            
            # Post to chatter if available
            for product in self:
                if product.wc_sync_enabled and product.wc_connection_id:
                    try:
                        # Try to use message_post (requires mail.thread)
                        product.with_context(mail_create_nosubscribe=True).message_post(
                            body=message,
                            subject=_('WooCommerce Sale Price Updated'),
                            message_type='notification',
                        )
                    except Exception as e:
                        _logger.warning(f"Could not post message to chatter: {e}")
                    
                    _logger.info(f"Manual sale price updated for {product.name}: {message}")
        
        return result
    
    def _get_mapped_odoo_fields(self):
        """Get list of Odoo fields that are mapped in field mappings"""
        self.ensure_one()
        
        if not self.wc_connection_id:
            return []
        

        mappings = self.env['woocommerce.field.mapping'].search([
            ('connection_id', '=', self.wc_connection_id.id),
            ('is_active', '=', True),
            ('mapping_direction', 'in', ['odoo_to_wc', 'bidirectional']),
        ])
        

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

            updated_fields = self.env.context.get('updated_fields', [])
            
            if updated_fields and self.wc_product_id:

                wc_product = self.env['woocommerce.product'].search([
                    ('wc_product_id', '=', self.wc_product_id),
                    ('connection_id', '=', self.wc_connection_id.id)
                ])
                if wc_product:
                    # Map Odoo fields to WooCommerce fields
                    wc_updated_fields = []
                    field_mapping = {
                        'list_price': 'regular_price',
                        'default_code': 'wc_sku',
                        'name': 'name',
                        'sale_ok': 'status',
                    }
                    for field in updated_fields:
                        if field in field_mapping:
                            wc_updated_fields.append(field_mapping[field])
                        elif field in ['description', 'description_sale']:
                            wc_updated_fields.append('wc_data')
                    
                    wc_product.with_context(updated_fields=wc_updated_fields if wc_updated_fields else updated_fields)._sync_to_woocommerce_store()
                    return
            

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
        

        stock_quantity = None
        if self.wc_connection_id:

            stock_mappings = self.env['woocommerce.field.mapping'].search([
                ('connection_id', '=', self.wc_connection_id.id),
                ('is_active', '=', True),
                ('mapping_direction', 'in', ['odoo_to_wc', 'bidirectional']),
                ('wc_field_name', 'ilike', 'stock')
            ])
            
            if stock_mappings:

                for mapping in stock_mappings:
                    if mapping.odoo_field_name:
                        try:
                            stock_value = getattr(self, mapping.odoo_field_name, 0)
                            if stock_value is not None:
                                stock_quantity = int(stock_value) if stock_value else 0
                                break
                        except (ValueError, TypeError, AttributeError):
                            continue
            


        
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
        

        if stock_quantity is not None:
            data['manage_stock'] = True
            data['stock_quantity'] = stock_quantity
            _logger.info(f"Including stock data: manage_stock=True, stock_quantity={stock_quantity}")
        else:
            _logger.info("No stock mapping found - preserving WooCommerce stock settings")
        
        if sale_price and float(sale_price) > 0:
            data['sale_price'] = sale_price
        

        _logger.info(f"Image sync check - wc_image_sync_enabled: {self.wc_image_sync_enabled}, has image_1920: {bool(self.image_1920)}")
        
        images_to_sync = []
        

        # First, ensure the inventory image (image_1920) is set as main image in WooCommerce product images
        # This ensures that whenever we sync, the inventory image is always the main image
        if self.wc_image_sync_enabled and self.image_1920:
            wc_product = self.env['woocommerce.product'].search([
                ('odoo_product_id', '=', self.id),
                ('connection_id', '=', self.wc_connection_id.id)
            ], limit=1)
            
            if wc_product:
                # Unset ALL existing main images first
                existing_main_images = wc_product.product_image_ids.filtered(lambda img: img.is_main_image)
                if existing_main_images:
                    existing_main_images.with_context(skip_wc_sync=True).write({'is_main_image': False})
                
                # Find or create the main image from inventory
                inventory_main_image = wc_product.product_image_ids.filtered(
                    lambda img: img.name and 'Main Image' in img.name
                )
                
                if inventory_main_image:
                    # Update existing main image record
                    inventory_main_image = inventory_main_image[0]
                    inventory_main_image.with_context(skip_wc_sync=True).write({
                        'image_1920': self.image_1920,
                        'is_main_image': True,
                        'sequence': 0,  # Main image should be first (sequence 0)
                        'sync_status': 'pending',
                    })
                    _logger.info(f"Updated main image from inventory for product {self.name}")
                else:
                    # Create new main image from inventory
                    inventory_main_image = self.env['woocommerce.product.image'].with_context(skip_wc_sync=True).create({
                        'product_id': wc_product.id,
                        'image_1920': self.image_1920,
                        'name': f"{self.name} - Main Image",
                        'is_main_image': True,
                        'sequence': 0,  # Main image should be first (sequence 0)
                        'sync_status': 'pending',
                    })
                    _logger.info(f"Created main image from inventory for product {self.name}")
        
        # Now build the images array for WooCommerce API
        if self.wc_image_sync_enabled:
            wc_product = self.env['woocommerce.product'].search([
                ('odoo_product_id', '=', self.id),
                ('connection_id', '=', self.wc_connection_id.id)
            ], limit=1)
            
            if wc_product and wc_product.product_image_ids:
                # Sort images: main image first (sequence 0), then others by sequence
                sorted_images = wc_product.product_image_ids.sorted(lambda img: (0 if img.is_main_image else 1, img.sequence))
                _logger.info(f"Found {len(sorted_images)} WooCommerce product images for {self.name}, main image: {sorted_images[0].name if sorted_images else 'None'}")

                for wc_image in sorted_images:
                    if self.wc_connection_id.image_upload_method == 'wordpress_media':
                        # WordPress Media Library method
                        if wc_image.sync_status == 'synced' and wc_image.wc_image_id and wc_image.wc_image_url:
                            _logger.info(f"Using WordPress Media Library image: {wc_image.name} (ID: {wc_image.wc_image_id}, Main: {wc_image.is_main_image})")
                            image_data = {
                                'id': wc_image.wc_image_id,
                                'src': wc_image.wc_image_url,
                                'name': wc_image.name or 'Product Image',
                                'alt': wc_image.alt_text or wc_image.name or ''
                            }
                            # Main image should be first in the array
                            if wc_image.is_main_image:
                                images_to_sync.insert(0, image_data)
                            else:
                                images_to_sync.append(image_data)
                            _logger.info(f"Added WordPress Media Library image to sync data: {wc_image.name}")
                        elif wc_image.image_1920 and wc_image.sync_status != 'synced':
                            _logger.info(f"Image {wc_image.name} needs to be synced to WordPress Media Library first")
                    else:
                        # Base64 method
                        if wc_image.image_1920:
                            _logger.info(f"Processing WooCommerce product image: {wc_image.name} (Main: {wc_image.is_main_image})")
                            image_data_processed = self._process_woocommerce_product_image(wc_image)
                            if image_data_processed:
                                image_data = {
                                    'src': image_data_processed,
                                    'name': wc_image.name or 'Product Image',
                                    'alt': wc_image.alt_text or wc_image.name or ''
                                }
                                # Main image should be first in the array
                                if wc_image.is_main_image:
                                    images_to_sync.insert(0, image_data)
                                else:
                                    images_to_sync.append(image_data)
                                _logger.info(f"Added WooCommerce product image to sync data: {wc_image.name}")
                            else:
                                _logger.warning(f"Failed to process WooCommerce product image: {wc_image.name}")
        
        if images_to_sync:
            data['images'] = images_to_sync
            _logger.info(f"Total images to sync for product {self.name}: {len(images_to_sync)}")
        else:
            _logger.info(f"No images to sync - wc_image_sync_enabled: {self.wc_image_sync_enabled}, main image: {bool(self.image_1920)}")
        

        custom_attributes = self._prepare_custom_attributes()
        

        existing_attributes = self._get_existing_woocommerce_attributes()
        if existing_attributes:

            if custom_attributes:

                existing_attr_map = {attr.get('slug', attr.get('name', '')): attr for attr in existing_attributes}
                

                for custom_attr in custom_attributes:
                    attr_slug = custom_attr.get('name', '')
                    if attr_slug in existing_attr_map:

                        existing_attr_map[attr_slug].update(custom_attr)
                    else:

                        existing_attributes.append(custom_attr)
                
                data['attributes'] = existing_attributes
            else:

                data['attributes'] = existing_attributes
        elif custom_attributes:

            data['attributes'] = custom_attributes
        
        return data
    
    def _get_existing_woocommerce_attributes(self):
        """Get existing attributes from WooCommerce to preserve them during updates"""
        self.ensure_one()
        
        if not self.wc_product_id or not self.wc_connection_id:
            return []
        
        try:

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
        

        mappings = self.env['woocommerce.field.mapping'].search([
            ('connection_id', '=', self.wc_connection_id.id),
            ('is_active', '=', True),
            ('mapping_direction', 'in', ['odoo_to_wc', 'bidirectional']),
        ])
        
        attributes = []
        
        for mapping in mappings:

            if mapping.odoo_field_name in ['name', 'list_price', 'default_code', 'description', 'description_sale']:
                continue
            

            if not mapping.wc_field_name or not mapping.wc_field_name.startswith('attributes.'):
                continue
            
            try:

                odoo_value = getattr(self, mapping.odoo_field_name, None)
                
                if odoo_value is None or odoo_value == False:
                    continue
                

                if isinstance(odoo_value, (int, float)):
                    odoo_value = str(odoo_value)
                elif hasattr(odoo_value, 'name'):
                    odoo_value = odoo_value.name
                


                final_value = str(odoo_value)
                

                wc_field_parts = mapping.wc_field_name.split('.')
                if len(wc_field_parts) >= 2:
                    attr_slug = wc_field_parts[1].replace('.options', '')
                    

                    self._ensure_woocommerce_attribute_exists(attr_slug, final_value)
                    

                    attributes.append({
                        'name': attr_slug,
                        'options': [final_value],
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

            import requests
            
            url = f"{self.wc_connection_id.store_url}/wp-json/wc/v3/products/attributes"
            headers = self.wc_connection_id._get_auth_headers()
            

            response = requests.get(url, headers=headers, timeout=600)
            
            if response.status_code == 200:
                attributes = response.json()
                existing_attr = None
                
                for attr in attributes:
                    if attr.get('slug') == attr_slug:
                        existing_attr = attr
                        break
                
                if existing_attr:

                    attr_id = existing_attr['id']
                    terms_url = f"{url}/{attr_id}/terms"
                    terms_response = requests.get(terms_url, headers=headers, timeout=600)
                    
                    if terms_response.status_code == 200:
                        terms = terms_response.json()
                        existing_term = any(term.get('name', '').lower() == option_value.lower() for term in terms)
                        
                        if not existing_term:

                            term_data = {'name': option_value}
                            requests.post(terms_url, headers=headers, json=term_data, timeout=600)
                            _logger.info(f"Created WooCommerce attribute term: {option_value} for {attr_slug}")
                else:

                    attr_data = {
                        'name': attr_slug.replace('pa_', '').replace('-', ' ').title(),
                        'slug': attr_slug,
                        'type': 'select',
                        'order_by': 'menu_order',
                        'has_archives': False
                    }
                    
                    create_response = requests.post(url, headers=headers, json=attr_data, timeout=600)
                    
                    if create_response.status_code == 201:
                        new_attr = create_response.json()
                        attr_id = new_attr['id']
                        

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
            # Sync list_price to regular_price (base price before promotion)
            new_list_price = float(vals['list_price'])
            wc_update_vals['regular_price'] = new_list_price
            
            # When list_price is updated in Inventory, also update sale_price in WooCommerce
            # Priority: 1) Manual sale price (if set), 2) Recalculate from promotions, 3) Same as list_price
            if self.wc_manual_sale_price and self.wc_manual_sale_price > 0:
                # Manual sale price is set - keep it
                wc_update_vals['sale_price'] = self.wc_manual_sale_price
                _logger.info(f"Keeping manual sale price {self.wc_manual_sale_price} for product {self.name} after list_price update to {new_list_price}")
            else:
                # No manual sale price - set sale_price to list_price initially
                # It will be recalculated from promotions if any exist (in woocommerce.product.write())
                wc_update_vals['sale_price'] = new_list_price
                _logger.info(f"Setting sale_price to list_price {new_list_price} for product {self.name}, will be recalculated from promotions if any exist")
        
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
            

            updated_fields = list(wc_update_vals.keys())
            _logger.info(f"Product template updating WooCommerce product with fields: {updated_fields}")
            
            # Determine if we should recalculate promotions
            # Only recalculate if there's no manual sale price set
            has_manual_sale_price = self.wc_manual_sale_price and self.wc_manual_sale_price > 0
            should_recalculate_promotions = not has_manual_sale_price
            
            # If sale_price is in the update, make sure it's included in updated_fields for sync
            if 'sale_price' in wc_update_vals and 'sale_price' not in updated_fields:
                updated_fields.append('sale_price')
            
            # Skip syncing back to Odoo product to prevent loops
            # IMPORTANT: Don't set importing_from_woocommerce=True, so the write method will sync to WooCommerce store
            wc_product = wc_product.with_context(
                updated_fields=updated_fields,
                skip_regular_price_sync=['regular_price'] if 'regular_price' in updated_fields else [],
                allow_promotion_recalculation=should_recalculate_promotions,  # Allow recalculation only if no manual sale price
                skip_promotion_recalculation=has_manual_sale_price,  # Skip if manual sale price is set
                from_odoo_product=True  # Flag to indicate this update is from Odoo product
            )
            wc_product.write(wc_update_vals)
            
            _logger.info(f"Updated WooCommerce product table for {self.name}: regular_price={wc_update_vals.get('regular_price')}, sale_price={wc_update_vals.get('sale_price')}, recalculate_promotions={should_recalculate_promotions}")
            
            # Force sync to WooCommerce store after updating the table
            # The write method should handle this, but let's ensure it happens
            if wc_product.connection_id and wc_product.wc_product_id:
                try:
                    wc_product._sync_to_woocommerce_store()
                    wc_product.write({
                        'sync_status': 'synced',
                        'last_sync': fields.Datetime.now(),
                        'sync_error': False,
                    })
                    _logger.info(f"Synced WooCommerce product {wc_product.name} to WooCommerce store after Odoo update")
                except Exception as e:
                    _logger.error(f"Error syncing WooCommerce product {wc_product.name} to store: {e}")
                    wc_product.write({
                        'sync_status': 'error',
                        'sync_error': str(e),
                    })
            
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
    
    def _process_product_image_for_sync(self, product):
        """Process product image when it changes - ensure inventory image is always the main image in WooCommerce"""
        if not product.image_1920 or not product.wc_product_id or not product.wc_connection_id:
            return
        
        try:
            wc_product = self.env['woocommerce.product'].search([
                ('wc_product_id', '=', product.wc_product_id),
                ('connection_id', '=', product.wc_connection_id.id)
            ], limit=1)
            
            if not wc_product:
                _logger.warning(f"WooCommerce product record not found for {product.name}")
                return
            
            # Unset ALL existing main images first
            existing_main_images = wc_product.product_image_ids.filtered(lambda img: img.is_main_image)
            if existing_main_images:
                existing_main_images.with_context(skip_wc_sync=True).write({'is_main_image': False})
            
            # Find or create the main image from inventory
            # First, check if there's already an image with the same data (to avoid duplicates)
            inventory_main_image = wc_product.product_image_ids.filtered(
                lambda img: img.name and 'Main Image' in img.name
            )
            
            if inventory_main_image:
                # Update existing main image record
                inventory_main_image = inventory_main_image[0]
                inventory_main_image.with_context(skip_wc_sync=True).write({
                    'image_1920': product.image_1920,
                    'is_main_image': True,
                    'sequence': 0,  # Main image should be first
                    'sync_status': 'pending',
                })
                _logger.info(f"Updated main image from inventory for product {product.name}")
            else:
                # Create new main image from inventory
                inventory_main_image = self.env['woocommerce.product.image'].with_context(skip_wc_sync=True).create({
                    'product_id': wc_product.id,
                    'image_1920': product.image_1920,
                    'name': f"{product.name} - Main Image",
                    'is_main_image': True,
                    'sequence': 0,  # Main image should be first
                    'sync_status': 'pending',
                })
                _logger.info(f"Created main image from inventory for product {product.name}")
            
            # Ensure it's marked as main and sync it
            if inventory_main_image:
                # Make sure it's the only main image
                other_images = wc_product.product_image_ids - inventory_main_image
                if other_images:
                    other_images.filtered(lambda img: img.is_main_image).with_context(skip_wc_sync=True).write({'is_main_image': False})
                
                # Sync the main image to WooCommerce if pending
                if inventory_main_image.sync_status == 'pending':
                    try:
                        inventory_main_image.action_sync_to_woocommerce()
                        _logger.info(f"Synced main image to WooCommerce for product {product.name}")
                    except Exception as e:
                        _logger.error(f"Error syncing main image to WooCommerce: {e}")
                    
        except Exception as e:
            _logger.error(f"Error processing product image for sync: {e}")
    
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
        """Redirect to WooCommerce product form view"""
        self.ensure_one()
        
        if not self.wc_product_id or not self.wc_connection_id:
            raise ValidationError(_('This product is not linked to a WooCommerce product.'))
        
        wc_product = self.env['woocommerce.product'].search([
            ('wc_product_id', '=', self.wc_product_id),
            ('connection_id', '=', self.wc_connection_id.id)
        ])
        
        if not wc_product:
            raise ValidationError(_('WooCommerce product record not found.'))
        
        # Get the form view ID
        form_view = self.env.ref('woocommerce_integration.view_woocommerce_product_form')
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('WooCommerce Product - %s') % wc_product.name,
            'res_model': 'woocommerce.product',
            'res_id': wc_product.id,
            'view_mode': 'form',
            'view_id': form_view.id,
            'target': 'current',
            'context': {
                'default_product_id': wc_product.id,
                'default_name': wc_product.name,
                'active_id': wc_product.id,
            },
        }