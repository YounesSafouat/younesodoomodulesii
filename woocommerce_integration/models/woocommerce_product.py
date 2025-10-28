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
        help='Sale price in WooCommerce'
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
    ], string='Status')
    
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
    
    def write(self, vals):
        """Override write to sync changes to WooCommerce and Odoo product"""
        sync_fields = ['name', 'price', 'regular_price', 'sale_price', 'status', 'wc_sku', 'wc_data']
        
        sync_needed = any(key in vals for key in sync_fields)
        updated_fields = [key for key in vals.keys() if key in sync_fields]
        
        # Check if we're importing from WooCommerce - if so, don't sync back
        importing_from_woocommerce = self.env.context.get('importing_from_woocommerce', False)
        
        # Set context before calling super().write() so it's available during sync
        if updated_fields and not importing_from_woocommerce:
            self = self.with_context(updated_fields=updated_fields)
        
        result = super(WooCommerceProduct, self).write(vals)
        
        for record in self:
            if sync_needed and record.connection_id and record.wc_product_id and not importing_from_woocommerce:
                try:
                    record._sync_to_woocommerce_store()
                    
                    if record.odoo_product_id:
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
        
        # Get the fields that were actually updated
        updated_fields = self.env.context.get('updated_fields', [])
        _logger.info(f"WooCommerce sync called with updated_fields: {updated_fields}")
        
        if updated_fields:
            # Only send the changed fields
            wc_data = self._prepare_partial_woocommerce_data(updated_fields)
            if wc_data:
                _logger.info(f"Syncing WooCommerce product {self.wc_product_id} with partial data (updated fields: {updated_fields}): {wc_data}")
            else:
                _logger.warning(f"No WooCommerce data prepared for fields: {updated_fields}")
                return
        else:
            # Fallback to full data if no specific fields were updated
            _logger.info("No updated_fields in context, using full data sync")
            if self.odoo_product_id:
                wc_data = self.odoo_product_id._prepare_woocommerce_data()
            else:
                # Fallback to basic data if no Odoo product linked
                wc_data = {
                    'name': self.name,
                    'regular_price': str(self.regular_price) if self.regular_price else '',
                    'sale_price': str(self.sale_price) if self.sale_price else '',
                    'status': self.status,
                    'sku': self.wc_sku or '',
                }
                
                if not self.sale_price or self.sale_price <= 0:
                    wc_data['sale_price'] = ''
                    wc_data['regular_price'] = str(self.price) if self.price else str(self.regular_price)
            
            _logger.info(f"Syncing WooCommerce product {self.wc_product_id} with full data: {wc_data}")
        
        self.connection_id.update_product(self.wc_product_id, wc_data)
    
    def _prepare_partial_woocommerce_data(self, updated_fields):
        """Prepare only the changed fields for WooCommerce API"""
        self.ensure_one()
        wc_data = {}
        
        # Filter out non-WooCommerce fields
        wc_fields = ['name', 'price', 'regular_price', 'sale_price', 'status', 'wc_sku']
        actual_updated_fields = [field for field in updated_fields if field in wc_fields]
        
        if not actual_updated_fields:
            _logger.warning(f"No valid WooCommerce fields in updated_fields: {updated_fields}")
            return {}
        
        # Map Odoo fields to WooCommerce fields
        field_mapping = {
            'name': 'name',
            'price': 'regular_price',
            'regular_price': 'regular_price', 
            'sale_price': 'sale_price',
            'status': 'status',
            'wc_sku': 'sku',
        }
        
        for field in actual_updated_fields:
            if field in field_mapping:
                wc_field = field_mapping[field]
                
                if field == 'name':
                    wc_data[wc_field] = self.name or 'Untitled Product'
                elif field in ['price', 'regular_price']:
                    wc_data[wc_field] = str(self.regular_price) if self.regular_price else '0.00'
                elif field == 'sale_price':
                    if self.sale_price and self.sale_price > 0:
                        wc_data[wc_field] = str(self.sale_price)
                    else:
                        wc_data[wc_field] = ''
                elif field == 'status':
                    wc_data[wc_field] = self.status
                elif field == 'wc_sku':
                    wc_data[wc_field] = self.wc_sku or ''
        
        # If we're updating prices, make sure we handle the sale price logic
        if 'sale_price' in actual_updated_fields or 'regular_price' in actual_updated_fields or 'price' in actual_updated_fields:
            if self.sale_price and self.sale_price > 0:
                wc_data['sale_price'] = str(self.sale_price)
                wc_data['regular_price'] = str(self.regular_price) if self.regular_price else '0.00'
            else:
                wc_data['sale_price'] = ''
                wc_data['regular_price'] = str(self.regular_price) if self.regular_price else '0.00'
        
        _logger.info(f"Prepared partial WooCommerce data for fields {actual_updated_fields}: {wc_data}")
        return wc_data
    
    def _sync_to_odoo_product(self):
        """Sync changes to the linked Odoo product"""
        self.ensure_one()
        
        if not self.odoo_product_id:
            return
        
        odoo_vals = {}
        
        if 'name' in self._context.get('updated_fields', []):
            odoo_vals['name'] = self.name
        
        if 'sale_price' in self._context.get('updated_fields', []):
            if self.sale_price and self.sale_price > 0:
                odoo_vals['list_price'] = self.sale_price
            elif self.regular_price and self.regular_price > 0:
                odoo_vals['list_price'] = self.regular_price
            elif self.price and self.price > 0:
                odoo_vals['list_price'] = self.price
        
        if 'wc_sku' in self._context.get('updated_fields', []):
            odoo_vals['default_code'] = self.wc_sku
        
        if 'status' in self._context.get('updated_fields', []):
            odoo_vals['sale_ok'] = self.status == 'publish'
        
        if odoo_vals:
            odoo_vals['wc_auto_sync'] = False
            self.odoo_product_id.write(odoo_vals)
            
            self.env.cr.commit()
            self.odoo_product_id.write({'wc_auto_sync': True})
            
            _logger.info(f"Updated Odoo product {self.odoo_product_id.name} with: {odoo_vals}")
    
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
            wc_data = eval(self.wc_data) if self.wc_data else {}
            
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
                response = requests.get(image_url, timeout=600)  # 10 minutes
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
        """Sync product attributes"""
        attributes_data = wc_data.get('attributes', [])
        if not attributes_data:
            return
        
        try:
            for attr_data in attributes_data:
                attr_name = attr_data.get('name', '')
                attr_options = attr_data.get('options', [])
                
                if attr_name and attr_options:
                    attribute = self.env['product.attribute'].search([('name', '=', attr_name)], limit=1)
                    if not attribute:
                        attribute = self.env['product.attribute'].create({
                            'name': attr_name,
                            'create_variant': 'no_variant',
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
        """Sync product data from WooCommerce"""
        self.ensure_one()
        
        try:
            wc_data = self.connection_id.get_product(self.wc_product_id)
            
            self.write({
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
            
            if self.odoo_product_id:
                self.odoo_product_id.write({
                    'list_price': self.price or self.regular_price or 0,
                })
            
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
    
    @api.model
    def _cron_sync_products(self):
        """Cron job to automatically sync products from WooCommerce"""
        _logger.info("Starting WooCommerce product sync cron job")
        
        connections = self.env['woocommerce.connection'].search([
            ('active', '=', True),
            ('connection_status', '=', 'success')
        ])
        
        for connection in connections:
            try:
                products_to_sync = self.search([
                    ('connection_id', '=', connection.id),
                    ('sync_status', 'in', ['pending', 'error'])
                ])
                
                for product in products_to_sync:
                    try:
                        product.action_sync_from_woocommerce()
                    except Exception as e:
                        _logger.error(f"Error syncing product {product.id}: {e}")
                
                _logger.info(f"Synced {len(products_to_sync)} products for connection {connection.name}")
                
            except Exception as e:
                _logger.error(f"Error in WooCommerce sync cron for connection {connection.name}: {e}")
        
        _logger.info("WooCommerce product sync cron job completed")
