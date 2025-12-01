import base64
import requests
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class WooCommerceProduct(models.Model):
    _name = 'woocommerce.product'
    _description = 'WooCommerce Product'
    _order = 'wc_product_id'

    name = fields.Char(
        string='Product Name',
        required=True,
        help='Product name from WooCommerce'
    )
    
    wc_product_id = fields.Integer(
        string='WooCommerce Product ID',
        required=True,
        help='Product ID in WooCommerce'
    )
    
    wc_sku = fields.Char(
        string='WooCommerce SKU',
        help='Product SKU in WooCommerce'
    )
    
    connection_id = fields.Many2one(
        'woocommerce.connection',
        string='Connection',
        required=True,
        ondelete='cascade',
        help='WooCommerce connection'
    )
    
    odoo_product_id = fields.Many2one(
        'product.template',
        string='Odoo Product',
        help='Corresponding Odoo product'
    )
    
    wc_data = fields.Text(
        string='WooCommerce Data',
        help='Raw JSON data from WooCommerce'
    )
    
    wc_data_formatted = fields.Text(
        string='Formatted WooCommerce Data',
        compute='_compute_wc_data_formatted',
        help='Formatted JSON data from WooCommerce for better readability'
    )
    
    price = fields.Float(
        string='Price',
        help='Product price in WooCommerce'
    )
    
    regular_price = fields.Float(
        string='Regular Price',
        help='Regular price in WooCommerce'
    )
    
    sale_price = fields.Float(
        string='Sale Price',
        readonly=True,
        help='Sale price calculated from active promotions. If no promotion is active, it equals the regular price. This field is automatically calculated and cannot be edited.'
    )
    
    stock_status = fields.Selection([
        ('instock', 'In Stock'),
        ('outofstock', 'Out of Stock'),
        ('onbackorder', 'On Backorder'),
    ], string='Stock Status')
    
    status = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('private', 'Private'),
        ('publish', 'Published'),
    ], string='Status', default='draft', required=True,
        help='Product status in WooCommerce. Required when pushing to WooCommerce.')
    
    featured = fields.Boolean(
        string='Featured',
        help='Is this a featured product?'
    )
    
    categories = fields.Text(
        string='Categories',
        help='Product categories in WooCommerce'
    )
    
    category_ids = fields.Many2many(
        'woocommerce.category',
        string='WooCommerce Categories',
        help='Mapped WooCommerce categories for this product'
    )
    
    images = fields.Text(
        string='Images',
        help='Product images data from WooCommerce'
    )
    
    attributes = fields.Text(
        string='Attributes',
        help='Product attributes from WooCommerce'
    )
    
    last_sync = fields.Datetime(
        string='Last Sync',
        help='Last time this product was synchronized'
    )
    
    sync_status = fields.Selection([
        ('pending', 'Pending'),
        ('synced', 'Synced'),
        ('error', 'Error'),
    ], string='Sync Status', default='pending')
    
    sync_error = fields.Text(
        string='Sync Error',
        help='Last synchronization error'
    )
    
    product_image_ids = fields.One2many(
        'woocommerce.product.image',
        'product_id',
        string='Product Images',
        help='Multiple images for this product'
    )
    
    image_count = fields.Integer(
        string='Image Count',
        compute='_compute_image_count',
        help='Number of images for this product'
    )
    
    has_unsynced_images = fields.Boolean(
        string='Has Unsynced Images',
        compute='_compute_has_unsynced_images',
        help='True if there are images that need to be synced to WooCommerce'
    )
    

    is_variable_product = fields.Boolean(
        string='Variable Product',
        compute='_compute_is_variable_product',
        help='True if this is a WooCommerce variable product with variations'
    )
    
    variant_mapping_ids = fields.One2many(
        'woocommerce.variant.mapping',
        'product_id',
        string='Variations',
        help='WooCommerce product variations mapped to Odoo variants'
    )
    
    variant_count = fields.Integer(
        string='Variation Count',
        compute='_compute_variant_count',
        help='Number of variations for this product'
    )
    
    @api.depends('wc_data')
    def _compute_is_variable_product(self):
        """Check if product is a variable product"""
        for record in self:
            try:
                if record.wc_data:
                    import json
                    wc_data = json.loads(record.wc_data) if isinstance(record.wc_data, str) else record.wc_data
                    record.is_variable_product = wc_data.get('type') == 'variable'
                else:
                    record.is_variable_product = False
            except:
                record.is_variable_product = False
    
    @api.depends('variant_mapping_ids')
    def _compute_variant_count(self):
        """Compute the number of variations"""
        for record in self:
            record.variant_count = len(record.variant_mapping_ids)
    
    @api.depends('product_image_ids')
    def _compute_image_count(self):
        """Compute the number of images for this product"""
        for record in self:
            record.image_count = len(record.product_image_ids)
    
    @api.depends('wc_data')
    def _compute_wc_data_formatted(self):
        """Format WooCommerce JSON data for better readability"""
        import json
        for record in self:
            if record.wc_data:
                try:
                    data = json.loads(record.wc_data)
                    record.wc_data_formatted = json.dumps(data, indent=4, ensure_ascii=False)
                except:
                    record.wc_data_formatted = record.wc_data
            else:
                record.wc_data_formatted = ''
    
    @api.depends('product_image_ids', 'product_image_ids.sync_status', 'product_image_ids.image_1920')
    def _compute_has_unsynced_images(self):
        """Check if there are images that need to be synced"""
        for record in self:
            record.has_unsynced_images = bool(record.product_image_ids.filtered(
                lambda img: img.image_1920 and img.sync_status != 'synced'
            ))
    
    def action_sync_all_images(self):
        """Sync all unsynced images to WooCommerce"""
        self.ensure_one()
        
        unsynced_images = self.product_image_ids.filtered(
            lambda img: img.image_1920 and img.sync_status != 'synced'
        )
        
        if not unsynced_images:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Info'),
                    'message': _('No images need to be synced!'),
                    'type': 'info',
                }
            }
        
        synced_count = 0
        error_count = 0
        
        for image in unsynced_images:
            try:
                image.action_sync_to_woocommerce()
                synced_count += 1
            except Exception as e:
                _logger.error(f"Failed to sync image {image.name}: {str(e)}")
                error_count += 1
        
        if error_count == 0:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Successfully synced %d images to WooCommerce!') % synced_count,
                    'type': 'success',
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Partial Success'),
                    'message': _('Synced %d images successfully, %d failed. Check individual image errors.') % (synced_count, error_count),
                    'type': 'warning',
                }
            }
    
    def _ensure_inventory_image_is_main(self):
        """Ensure that the Odoo inventory image (image_1920) is always the main image in WooCommerce product images"""
        self.ensure_one()
        
        if not self.odoo_product_id or not self.odoo_product_id.image_1920:
            return
        
        try:
            # Unset ALL existing main images first
            existing_main_images = self.product_image_ids.filtered(lambda img: img.is_main_image)
            if existing_main_images:
                existing_main_images.with_context(skip_wc_sync=True).write({'is_main_image': False})
            
            # Find or create the main image from inventory
            inventory_main_image = self.product_image_ids.filtered(
                lambda img: img.name and 'Main Image' in img.name
            )
            
            if inventory_main_image:
                # Update existing main image record
                inventory_main_image = inventory_main_image[0]
                inventory_main_image.with_context(skip_wc_sync=True).write({
                    'image_1920': self.odoo_product_id.image_1920,
                    'is_main_image': True,
                    'sequence': 0,  # Main image should be first
                    'sync_status': 'pending' if inventory_main_image.image_1920 != self.odoo_product_id.image_1920 else inventory_main_image.sync_status,
                })
                _logger.debug(f"Updated main image from inventory for product {self.name}")
            else:
                # Create new main image from inventory
                inventory_main_image = self.env['woocommerce.product.image'].with_context(skip_wc_sync=True).create({
                    'product_id': self.id,
                    'image_1920': self.odoo_product_id.image_1920,
                    'name': f"{self.odoo_product_id.name} - Main Image",
                    'is_main_image': True,
                    'sequence': 0,  # Main image should be first
                    'sync_status': 'pending',
                })
                _logger.info(f"Created main image from inventory for product {self.name}")
            
            # Ensure it's the only main image
            other_images = self.product_image_ids - inventory_main_image
            if other_images:
                other_images.filtered(lambda img: img.is_main_image).with_context(skip_wc_sync=True).write({'is_main_image': False})
                
        except Exception as e:
            _logger.error(f"Error ensuring inventory image is main for product {self.name}: {e}")
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to ensure sale_price is set to regular_price initially"""
        for vals in vals_list:
            # If regular_price is set but sale_price is not, set sale_price = regular_price
            if 'regular_price' in vals and 'sale_price' not in vals:
                if vals.get('regular_price') and vals['regular_price'] > 0:
                    vals['sale_price'] = vals['regular_price']
        
        products = super(WooCommerceProduct, self).create(vals_list)
        
        # After creation, recalculate sale_price from promotions if needed
        for product in products:
            if product.regular_price and product.odoo_product_id and product.connection_id:
                # Recalculate from promotions (will set to regular_price if no promotion)
                product._recalculate_sale_price_from_promotions(new_regular_price=product.regular_price)
        
        return products
    
    def write(self, vals):
        """Override write to sync changes to WooCommerce and Odoo product"""
        # Protect sensitive fields from being changed
        sensitive_fields = ['wc_product_id', 'connection_id', 'odoo_product_id']
        for field in sensitive_fields:
            if field in vals:
                for record in self:
                    if record[field] and vals[field] != record[field]:
                        raise UserError(_('Cannot change %s. This is a sensitive field that links the product to WooCommerce. Changing it could break synchronization.') % field)
        
        sync_fields = ['name', 'regular_price', 'sale_price', 'status', 'wc_sku', 'wc_data']
        
        sync_needed = any(key in vals for key in sync_fields)
        updated_fields = [key for key in vals.keys() if key in sync_fields]
        

        importing_from_woocommerce = self.env.context.get('importing_from_woocommerce', False)
        

        if updated_fields and not importing_from_woocommerce:
            self = self.with_context(updated_fields=updated_fields)
        
        result = super(WooCommerceProduct, self).write(vals)
        
        # Ensure inventory image is always the main image
        for record in self:
            if record.odoo_product_id and record.odoo_product_id.image_1920:
                record._ensure_inventory_image_is_main()
        
        for record in self:
            # Check sync direction before syncing to Odoo
            # Only sync if direction is bidirectional or wc_to_odoo
            sync_direction = None
            if record.odoo_product_id:
                sync_direction = record.odoo_product_id.wc_sync_direction
            
            # Sync regular_price to Odoo product list_price (bidirectional sync)
            # Skip if update is coming from Odoo product to prevent loop
            # Only sync if sync direction allows it (bidirectional or wc_to_odoo)
            skip_regular_price_sync = self.env.context.get('skip_regular_price_sync', [])
            if ('regular_price' in vals and record.odoo_product_id and 
                not importing_from_woocommerce and 'regular_price' not in skip_regular_price_sync and
                sync_direction in ['bidirectional', 'wc_to_odoo']):
                try:
                    # Update Odoo product price to match regular_price
                    record.odoo_product_id.with_context(skip_wc_sync=True).write({
                        'list_price': vals['regular_price']
                    })
                    _logger.info(f"Synced regular_price {vals['regular_price']} to Odoo product {record.odoo_product_id.name} list_price (sync_direction: {sync_direction})")
                except Exception as e:
                    _logger.error(f"Error syncing regular_price to Odoo product: {e}")
            
            # If regular_price changed, recalculate sale_price (from promotions or set to regular_price)
            # Do this after the write so the new regular_price value is available
            # Also allow recalculation when price changes from Odoo (product.template)
            # Skip if we're already recalculating to prevent recursion
            # IMPORTANT: If sale_price was explicitly set in vals (e.g., from list_price update), 
            # only recalculate if allow_promotion_recalculation is True and sale_price wasn't explicitly set
            skip_recalc = self.env.context.get('skip_promotion_recalculation', False)
            allow_recalc = self.env.context.get('allow_promotion_recalculation', False)
            sale_price_explicitly_set = 'sale_price' in vals
            
            if 'regular_price' in vals and record.odoo_product_id and (not importing_from_woocommerce or allow_recalc) and not skip_recalc:
                # Only recalculate if sale_price wasn't explicitly set, or if we're allowing recalculation
                if not sale_price_explicitly_set or allow_recalc:
                    # The value is already written, so we can use it directly
                    # Use the new price from vals (it's already in the record after write)
                    new_regular_price = vals.get('regular_price')
                    # Recalculate sale_price from promotions (will set to regular_price if no promotion)
                    record._recalculate_sale_price_from_promotions(new_regular_price=new_regular_price)
                    # Update sync fields to include sale_price if it was recalculated
                    if 'sale_price' not in updated_fields:
                        updated_fields.append('sale_price')
                        sync_needed = True
                else:
                    # sale_price was explicitly set, keep it as is
                    _logger.info(f"Skipping promotion recalculation for {record.name} - sale_price was explicitly set to {vals.get('sale_price')}")
            elif 'regular_price' in vals and not skip_recalc:
                # If no odoo_product_id, still ensure sale_price = regular_price when no promotion
                new_regular_price = vals.get('regular_price')
                if new_regular_price and (not record.sale_price or record.sale_price == 0):
                    # If sale_price is not set, set it to regular_price (will be recalculated by promotion logic if needed)
                    record.with_context(skip_promotion_recalculation=True).write({'sale_price': new_regular_price})
            
            if sync_needed and record.connection_id and record.wc_product_id and not importing_from_woocommerce:
                try:
                    record._sync_to_woocommerce_store()
                    
                    # Sync other fields to Odoo if sync direction allows it
                    if record.odoo_product_id and 'regular_price' not in vals:
                        sync_direction = record.odoo_product_id.wc_sync_direction
                        if sync_direction in ['bidirectional', 'wc_to_odoo']:
                            # Only sync other fields if regular_price wasn't already synced above
                            record._sync_to_odoo_product()
                    
                    record.write({
                        'sync_status': 'synced',
                        'last_sync': fields.Datetime.now(),
                        'sync_error': False,
                    })
                    
                except Exception as e:
                    _logger.error(f"Error syncing WooCommerce product {record.name}: {e}")
                    record.write({
                        'sync_status': 'error',
                        'sync_error': str(e),
                    })
        
        return result
    
    def _sync_to_woocommerce_store(self):
        """Sync changes to the actual WooCommerce store"""
        self.ensure_one()
        

        updated_fields = self.env.context.get('updated_fields', [])
        _logger.info(f"WooCommerce sync called with updated_fields: {updated_fields}")
        
        if updated_fields:

            wc_data = self._prepare_partial_woocommerce_data(updated_fields)
            if wc_data:
                _logger.info(f"Syncing WooCommerce product {self.wc_product_id} with partial data (updated fields: {updated_fields}): {wc_data}")
            else:
                _logger.warning(f"No WooCommerce data prepared for fields: {updated_fields}")
                return
        else:

            _logger.info("No updated_fields in context, using full data sync")
            if self.odoo_product_id:
                wc_data = self.odoo_product_id._prepare_woocommerce_data()
            else:
                # Use regular_price as base price, sale_price only if set by promotions
                status_value = self.status if self.status in ['draft', 'pending', 'private', 'publish'] else 'draft'
                wc_data = {
                    'name': self.name or 'Untitled Product',
                    'regular_price': str(self.regular_price) if self.regular_price else '0.00',
                    'status': status_value,
                    'sku': self.wc_sku or '',
                }
                # Always include sale_price (calculated from promotions or equals regular_price)
                # Ensure sale_price is calculated before syncing
                if not self.sale_price or self.sale_price == 0:
                    # If sale_price is not set, set it to regular_price (no promotion)
                    self.with_context(skip_promotion_recalculation=True).write({'sale_price': self.regular_price or 0})
                wc_data['sale_price'] = str(self.sale_price) if self.sale_price else str(self.regular_price or 0)
            
            _logger.info(f"Syncing WooCommerce product {self.wc_product_id} with full data: {wc_data}")
        



        if not self.wc_product_id or self.wc_product_id == 0:

            _logger.info(f"Creating new WooCommerce product (no ID yet)")

            wc_data.pop('id', None)
            response = self.connection_id.create_product(wc_data)
            
            if response and response.get('id'):

                self.write({
                    'wc_product_id': response['id'],
                    'sync_status': 'synced',
                    'last_sync': fields.Datetime.now(),
                    'sync_error': False,
                })
                _logger.info(f"Created new WooCommerce product with ID: {response['id']}")
            else:
                raise UserError(_('Failed to create product in WooCommerce: No ID returned'))
        else:

            _logger.info(f"Updating existing WooCommerce product {self.wc_product_id}")

            product_id = int(str(self.wc_product_id).replace(',', '').replace(' ', ''))
            self.connection_id.update_product(product_id, wc_data)
    
    def _prepare_partial_woocommerce_data(self, updated_fields):
        """Prepare only the changed fields for WooCommerce API"""
        self.ensure_one()
        wc_data = {}
        

        wc_fields = ['name', 'regular_price', 'sale_price', 'status', 'wc_sku']
        actual_updated_fields = [field for field in updated_fields if field in wc_fields]
        
        if not actual_updated_fields:
            _logger.warning(f"No valid WooCommerce fields in updated_fields: {updated_fields}")
            return {}
        
        # Map fields to WooCommerce API fields
        for field in actual_updated_fields:
            if field == 'name':
                wc_data['name'] = self.name or 'Untitled Product'
            elif field == 'regular_price':
                wc_data['regular_price'] = str(self.regular_price) if self.regular_price else '0.00'
            elif field == 'sale_price':
                if self.sale_price and self.sale_price > 0:
                    wc_data['sale_price'] = str(self.sale_price)
                else:
                    wc_data['sale_price'] = ''
            elif field == 'status':
                wc_data['status'] = self.status if self.status in ['draft', 'pending', 'private', 'publish'] else 'draft'
            elif field == 'wc_sku':
                wc_data['sku'] = self.wc_sku or ''
        

        # Handle price fields: regular_price is base price, sale_price always calculated
        if 'regular_price' in actual_updated_fields:
            wc_data['regular_price'] = str(self.regular_price) if self.regular_price else '0.00'
            # Always include sale_price (calculated from promotions or equals regular_price)
            if 'sale_price' not in actual_updated_fields:
                # Ensure sale_price is set (equals regular_price if not calculated from promotion)
                sale_price_value = self.sale_price if (self.sale_price and self.sale_price > 0) else (self.regular_price or 0)
                wc_data['sale_price'] = str(sale_price_value)
        
        if 'sale_price' in actual_updated_fields:
            # Always send sale_price (calculated from promotions or equals regular_price)
            if not self.sale_price or self.sale_price == 0:
                wc_data['sale_price'] = str(self.regular_price or 0)
            else:
                wc_data['sale_price'] = str(self.sale_price)
        
        _logger.info(f"Prepared partial WooCommerce data for fields {actual_updated_fields}: {wc_data}")
        return wc_data
    
    def _recalculate_sale_price_from_promotions(self, new_regular_price=None):
        """Recalculate sale_price based on active promotions when regular_price changes"""
        self.ensure_one()
        
        # Skip recalculation if manual sale price is being set
        if self.env.context.get('manual_sale_price_update', False):
            return
        
        # Check if product has manual sale price set
        if self.odoo_product_id and self.odoo_product_id.wc_manual_sale_price and self.odoo_product_id.wc_manual_sale_price > 0:
            # Manual sale price is set, don't recalculate from promotions
            return
        
        if not self.odoo_product_id or not self.connection_id:
            return
        
        # Use the provided new price or the current regular_price
        product = self.odoo_product_id
        regular_price = new_regular_price if new_regular_price is not None else (self.regular_price if self.regular_price > 0 else product.list_price)
        
        # Find active promotions that include this product
        now = fields.Datetime.now()
        active_promotions = self.env['woocommerce.promotion'].search([
            ('connection_id', '=', self.connection_id.id),
            ('active', '=', True),
            ('status', '=', 'active'),
            ('date_start', '<=', now),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', now),
        ])
        
        if not active_promotions:
            # No active promotions, set sale_price = regular_price
            if abs(self.sale_price - regular_price) > 0.01:  # Only update if different
                self.with_context(skip_promotion_recalculation=True).write({'sale_price': regular_price})
                _logger.info(f"No active promotions found, set sale_price = regular_price ({regular_price}) for {self.name}")
            return
        
        # Check if this product is in any active promotion
        applicable_promotion = None
        
        for promotion in active_promotions:
            # Check if product is directly in promotion
            if product.id in promotion.product_ids.ids:
                applicable_promotion = promotion
                break
            
            # Check if product category is in promotion
            if promotion.product_category_ids and product.categ_id.id in promotion.product_category_ids.ids:
                applicable_promotion = promotion
                break
        
        if applicable_promotion:
            # Recalculate sale_price based on promotion discount
            if applicable_promotion.discount_type == 'percentage':
                sale_price = regular_price * (1 - applicable_promotion.discount_value / 100)
            else:  # fixed
                sale_price = max(0, regular_price - applicable_promotion.discount_value)
            
            # Update sale_price (use context to prevent recursion)
            if abs(self.sale_price - sale_price) > 0.01:  # Only update if different
                self.with_context(skip_promotion_recalculation=True).write({'sale_price': sale_price})
                _logger.info(f"Recalculated sale_price for {self.name} based on promotion {applicable_promotion.name}: {sale_price} (regular: {regular_price})")
        else:
            # Product not in any active promotion, set sale_price = regular_price
            if abs(self.sale_price - regular_price) > 0.01:  # Only update if different
                self.with_context(skip_promotion_recalculation=True).write({'sale_price': regular_price})
                _logger.info(f"Product {self.name} not in any active promotion, set sale_price = regular_price ({regular_price})")
    
    def _sync_to_odoo_product(self):
        """Sync changes to the linked Odoo product"""
        self.ensure_one()
        
        if not self.odoo_product_id:
            return
        
        # Check sync direction - only sync if bidirectional or wc_to_odoo
        sync_direction = self.odoo_product_id.wc_sync_direction
        if sync_direction not in ['bidirectional', 'wc_to_odoo']:
            _logger.debug(f"Skipping sync to Odoo for {self.name} - sync_direction is {sync_direction}")
            return
        
        odoo_vals = {}
        updated_fields = self._context.get('updated_fields', [])
        
        if 'name' in updated_fields:
            odoo_vals['name'] = self.name
        
        # regular_price is synced directly in write() method, so skip it here
        # Only sync regular_price if it wasn't already synced
        if 'regular_price' in updated_fields and 'regular_price' not in self._context.get('skip_regular_price_sync', []):
            odoo_vals['list_price'] = self.regular_price or 0.0
        
        if 'wc_sku' in updated_fields:
            odoo_vals['default_code'] = self.wc_sku
        
        if 'status' in updated_fields:
            odoo_vals['sale_ok'] = self.status == 'publish'
        
        if odoo_vals:
            odoo_vals['wc_auto_sync'] = False
            self.odoo_product_id.with_context(skip_wc_sync=True).write(odoo_vals)
            
            self.env.cr.commit()
            self.odoo_product_id.write({'wc_auto_sync': True})
            
            _logger.info(f"Updated Odoo product {self.odoo_product_id.name} with: {odoo_vals} (sync_direction: {sync_direction})")
    
    def action_sync_to_woocommerce(self):
        """Manual action to sync to WooCommerce store"""
        self.ensure_one()
        
        try:

            for image in self.product_image_ids.filtered(lambda i: i.sync_status == 'pending'):
                try:
                    if image.image_1920:
                        image.action_sync_to_woocommerce()
                except Exception as e:
                    _logger.error(f"Error syncing image {image.name}: {e}")
            

            self._sync_to_woocommerce_store()
            

            self.write({
                'sync_status': 'synced',
                'last_sync': fields.Datetime.now(),
                'sync_error': False,
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Product and images synced to WooCommerce successfully!'),
                    'type': 'success',
                }
            }
            
        except Exception as e:
            _logger.error(f"Error syncing product {self.name} to WooCommerce: {e}")
            self.write({
                'sync_status': 'error',
                'sync_error': str(e),
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Failed to sync to WooCommerce: %s') % str(e),
                    'type': 'danger',
                }
            }
    
    def action_sync_to_odoo(self):
        """Manual action to sync to Odoo product"""
        self.ensure_one()
        
        if not self.odoo_product_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Warning'),
                    'message': _('No Odoo product linked to sync to.'),
                    'type': 'warning',
                }
            }
        
        try:
            self._sync_to_odoo_product()
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Product synced to Odoo successfully!'),
                    'type': 'success',
                }
            }
            
        except Exception as e:
            _logger.error(f"Error syncing product {self.name} to Odoo: {e}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Failed to sync to Odoo: %s') % str(e),
                    'type': 'danger',
                }
            }
    
    @api.model
    def create_from_wc_data(self, wc_data, connection_id):
        """Create WooCommerce product from WooCommerce API data"""
        connection = self.env['woocommerce.connection'].browse(connection_id)
        
        existing = self.search([
            ('wc_product_id', '=', wc_data.get('id')),
            ('connection_id', '=', connection_id)
        ])
        
        if existing:
            return existing
        
        vals = {
            'name': wc_data.get('name', ''),
            'wc_product_id': wc_data.get('id'),
            'wc_sku': wc_data.get('sku', ''),
            'connection_id': connection_id,
            'price': float(wc_data.get('price', 0)),
            'regular_price': float(wc_data.get('regular_price', 0)),
            'sale_price': float(wc_data.get('sale_price', 0)) if wc_data.get('sale_price') else 0,
            'stock_status': wc_data.get('stock_status', 'instock'),
            'status': wc_data.get('status', 'publish'),
            'featured': wc_data.get('featured', False),
            'wc_data': str(wc_data),
            'categories': str(wc_data.get('categories', [])),
            'images': str(wc_data.get('images', [])),
            'attributes': str(wc_data.get('attributes', [])),
            'last_sync': fields.Datetime.now(),
            'sync_status': 'synced',
        }
        
        return self.create(vals)
    
    def action_create_odoo_product(self):
        """Create corresponding Odoo product"""
        self.ensure_one()
        
        if self.odoo_product_id:
            raise UserError(_('This WooCommerce product already has a corresponding Odoo product.'))
        
        try:
            import json
            wc_data = json.loads(self.wc_data) if isinstance(self.wc_data, str) else (eval(self.wc_data) if self.wc_data else {})
            
            product_vals = {
                'name': self.name,
                'default_code': self.wc_sku or f'WC-{self.wc_product_id}',
                'list_price': self.price or self.regular_price or 0,
                'type': 'product',
                'sale_ok': True,
                'purchase_ok': True,
                'wc_product_id': self.wc_product_id,
                'wc_connection_id': self.connection_id.id,
            }
            
            odoo_product = self.env['product.template'].create(product_vals)
            
            self.odoo_product_id = odoo_product.id
            
            self._sync_categories(odoo_product, wc_data)
            
            self._sync_images(odoo_product, wc_data)
            

            if self.is_variable_product and self.connection_id.import_variants:
                self._sync_variants(odoo_product, wc_data)
            else:

                self._sync_attributes(odoo_product, wc_data)
            
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'product.template',
                'res_id': odoo_product.id,
                'view_mode': 'form',
                'target': 'current',
            }
            
        except Exception as e:
            _logger.error(f"Error creating Odoo product for WooCommerce product {self.id}: {e}")
            self.sync_status = 'error'
            self.sync_error = str(e)
            raise UserError(_('Failed to create Odoo product: %s') % str(e))
    
    def _sync_variants(self, odoo_product, wc_data):
        """Sync WooCommerce variations as Odoo variants"""
        self.ensure_one()
        
        if not self.connection_id.import_variants:
            return
        
        try:

            variations = self.connection_id.get_product_variations(self.wc_product_id)
            
            if not variations:
                _logger.info(f"No variations found for variable product {self.name}")
                return
            

            for variation_data in variations:

                variant_mapping = self.env['woocommerce.variant.mapping'].create_from_woocommerce_variation(
                    variation_data, self.id
                )
                

                if self.connection_id.auto_create_variants:
                    try:
                        variant_mapping.action_create_odoo_variant()
                    except Exception as e:
                        _logger.warning(f"Failed to auto-create variant for variation {variation_data.get('id')}: {e}")
            
            _logger.info(f"Synced {len(variations)} variations for product {self.name}")
            
        except Exception as e:
            _logger.error(f"Error syncing variants for product {self.name}: {e}")
    
    def action_import_variations(self):
        """Import variations from WooCommerce"""
        self.ensure_one()
        
        if not self.is_variable_product:
            raise UserError(_('This product is not a variable product.'))
        
        try:

            variations = self.connection_id.get_product_variations(self.wc_product_id)
            
            if not variations:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('No Variations'),
                        'message': _('No variations found for this product.'),
                        'type': 'warning',
                    }
                }
            

            created_count = 0
            for variation_data in variations:
                existing = self.env['woocommerce.variant.mapping'].search([
                    ('product_id', '=', self.id),
                    ('wc_variation_id', '=', variation_data.get('id'))
                ], limit=1)
                
                if not existing:
                    self.env['woocommerce.variant.mapping'].create_from_woocommerce_variation(
                        variation_data, self.id
                    )
                    created_count += 1
            

            if self.connection_id.auto_create_variants and self.odoo_product_id:
                for variant_mapping in self.variant_mapping_ids.filtered(lambda v: not v.odoo_variant_id):
                    try:
                        variant_mapping.action_create_odoo_variant()
                    except Exception as e:
                        _logger.warning(f"Failed to create variant: {e}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Variations Imported'),
                    'message': _('Imported %d variations. %d new mappings created.') % (len(variations), created_count),
                    'type': 'success',
                }
            }
            
        except Exception as e:
            _logger.error(f"Error importing variations: {e}")
            raise UserError(_('Failed to import variations: %s') % str(e))
    
    def _sync_categories(self, odoo_product, wc_data):
        """Sync product categories"""
        categories_data = wc_data.get('categories', [])
        if not categories_data:
            return
        
        category_names = [cat.get('name', '') for cat in categories_data if cat.get('name')]
        if category_names:
            main_category_name = category_names[0]
            
            category = self.env['product.category'].search([('name', '=', main_category_name)], limit=1)
            if not category:
                category = self.env['product.category'].create({
                    'name': main_category_name,
                })
            
            odoo_product.categ_id = category.id
    
    def _sync_images(self, odoo_product, wc_data):
        """Sync product images"""
        images_data = wc_data.get('images', [])
        if not images_data:
            return
        
        try:
            main_image = images_data[0]
            image_url = main_image.get('src', '')
            
            if image_url:
                response = requests.get(image_url, timeout=600)
                response.raise_for_status()
                
                attachment = self.env['ir.attachment'].create({
                    'name': f"{odoo_product.name}_main_image",
                    'type': 'binary',
                    'datas': base64.b64encode(response.content),
                    'res_model': 'product.template',
                    'res_id': odoo_product.id,
                    'public': True,
                })
                
                odoo_product.image_1920 = attachment.datas
                
        except Exception as e:
            _logger.warning(f"Failed to sync image for product {odoo_product.name}: {e}")
    
    def _sync_attributes(self, odoo_product, wc_data):
        """Sync product attributes (for simple products or when variant creation is skipped)"""
        attributes_data = wc_data.get('attributes', [])
        if not attributes_data:
            return
        
        try:
            for attr_data in attributes_data:
                attr_name = attr_data.get('name', '')
                attr_options = attr_data.get('options', [])
                
                if attr_name and attr_options:

                    create_variant = 'no_variant'
                    if self.connection_id.import_variants and self.connection_id.variant_attribute_mapping != 'skip':
                        create_variant = 'always'
                    
                    attribute = self.env['product.attribute'].search([('name', '=', attr_name)], limit=1)
                    if not attribute:
                        attribute = self.env['product.attribute'].create({
                            'name': attr_name,
                            'create_variant': create_variant,
                        })
                    
                    for option in attr_options:
                        value = self.env['product.attribute.value'].search([
                            ('name', '=', option),
                            ('attribute_id', '=', attribute.id)
                        ], limit=1)
                        
                        if not value:
                            self.env['product.attribute.value'].create({
                                'name': option,
                                'attribute_id': attribute.id,
                            })
            
        except Exception as e:
            _logger.warning(f"Failed to sync attributes for product {odoo_product.name}: {e}")
    
    def action_sync_from_woocommerce(self):
        """Sync product data from WooCommerce store to Odoo"""
        self.ensure_one()
        
        try:
            # Pull latest data from WooCommerce store
            wc_data = self.connection_id.get_product(self.wc_product_id)
            
            # Update WooCommerce product table with latest data from store
            # Use importing_from_woocommerce context to prevent syncing back to store
            self.with_context(importing_from_woocommerce=True).write({
                'wc_data': str(wc_data),
                'price': float(wc_data.get('price', 0)),
                'regular_price': float(wc_data.get('regular_price', 0)),
                'sale_price': float(wc_data.get('sale_price', 0)) if wc_data.get('sale_price') else 0,
                'stock_status': wc_data.get('stock_status', 'instock'),
                'status': wc_data.get('status', 'publish'),
                'featured': wc_data.get('featured', False),
                'categories': str(wc_data.get('categories', [])),
                'images': str(wc_data.get('images', [])),
                'attributes': str(wc_data.get('attributes', [])),
                'last_sync': fields.Datetime.now(),
                'sync_status': 'synced',
                'sync_error': False,
            })
            
            # Sync to Odoo product if sync direction allows it
            if self.odoo_product_id:
                sync_direction = self.odoo_product_id.wc_sync_direction
                if sync_direction in ['bidirectional', 'wc_to_odoo']:
                    odoo_vals = {
                        'name': wc_data.get('name', self.odoo_product_id.name),
                        'list_price': float(wc_data.get('regular_price', wc_data.get('price', 0)) or 0),
                        'default_code': wc_data.get('sku', self.odoo_product_id.default_code or ''),
                        'description': wc_data.get('description', self.odoo_product_id.description or ''),
                        'description_sale': wc_data.get('short_description', self.odoo_product_id.description_sale or ''),
                        'sale_ok': wc_data.get('status') == 'publish',
                        'wc_last_sync': fields.Datetime.now(),
                        'wc_sync_status': 'synced',
                    }
                    self.odoo_product_id.with_context(skip_wc_sync=True, importing_from_woocommerce=True).write(odoo_vals)
                    _logger.info(f"Synced WooCommerce product data to Odoo product {self.odoo_product_id.name} (sync_direction: {sync_direction})")
                else:
                    _logger.debug(f"Skipping sync to Odoo for {self.name} - sync_direction is {sync_direction}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Successful'),
                    'message': _('Product synchronized successfully from WooCommerce.'),
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            _logger.error(f"Error syncing product {self.id} from WooCommerce: {e}")
            self.sync_status = 'error'
            self.sync_error = str(e)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Failed'),
                    'message': _('Failed to sync product from WooCommerce: %s') % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
    
    def action_view_odoo_product(self):
        """View the corresponding Odoo product"""
        self.ensure_one()
        
        if not self.odoo_product_id:
            raise UserError(_('No corresponding Odoo product found.'))
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product.template',
            'res_id': self.odoo_product_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_view_variations(self):
        """View product variations"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Product Variations'),
            'res_model': 'woocommerce.variant.mapping',
            'view_mode': 'list,form',
            'domain': [('product_id', '=', self.id)],
            'context': {
                'default_product_id': self.id,
                'default_connection_id': self.connection_id.id,
            },
            'target': 'current',
        }
    
    @api.model
    def _cron_sync_products(self):
        """Cron job to automatically sync products from WooCommerce store to Odoo"""
        _logger.info("Starting WooCommerce product sync cron job (pulling from WooCommerce store)")
        
        connections = self.env['woocommerce.connection'].search([
            ('active', '=', True),
            ('connection_status', '=', 'success')
        ])
        
        _logger.info(f"Found {len(connections)} active connections")
        
        for connection in connections:
            try:
                # Find products that should be synced from WooCommerce (bidirectional or wc_to_odoo)
                products_to_sync = self.search([
                    ('connection_id', '=', connection.id),
                    ('odoo_product_id', '!=', False),  # Only products linked to Odoo
                    ('wc_product_id', '!=', False),  # Only products that exist in WooCommerce
                ])
                
                _logger.info(f"Connection {connection.name}: Found {len(products_to_sync)} products linked to Odoo")
                
                synced_count = 0
                error_count = 0
                skipped_no_direction = 0
                skipped_no_auto_sync = 0
                
                for product in products_to_sync:
                    # Check sync direction - only sync if bidirectional or wc_to_odoo
                    odoo_product = product.odoo_product_id
                    if not odoo_product:
                        _logger.debug(f"Product {product.name} has no linked Odoo product, skipping")
                        continue
                    
                    sync_direction = odoo_product.wc_sync_direction
                    if sync_direction not in ['bidirectional', 'wc_to_odoo']:
                        _logger.debug(f"Product {product.name} sync_direction is {sync_direction}, skipping (needs bidirectional or wc_to_odoo)")
                        skipped_no_direction += 1
                        continue
                    
                    # Only sync if auto_sync is enabled
                    if not odoo_product.wc_auto_sync:
                        _logger.debug(f"Product {product.name} has wc_auto_sync=False, skipping")
                        skipped_no_auto_sync += 1
                        continue
                    
                    try:
                        _logger.info(f"Syncing product {product.name} (ID: {product.wc_product_id}) from WooCommerce store...")
                        # Pull latest data from WooCommerce store
                        product.action_sync_from_woocommerce()
                        synced_count += 1
                        _logger.info(f"Successfully synced product {product.name} from WooCommerce")
                    except Exception as e:
                        _logger.error(f"Error syncing product {product.id} ({product.name}) from WooCommerce: {e}")
                        error_count += 1
                
                _logger.info(f"Connection {connection.name}: Synced {synced_count} products, {error_count} errors, {skipped_no_direction} skipped (wrong direction), {skipped_no_auto_sync} skipped (auto_sync disabled)")
                
            except Exception as e:
                _logger.error(f"Error in WooCommerce sync cron for connection {connection.name}: {e}")
        
        _logger.info("WooCommerce product sync cron job completed")
