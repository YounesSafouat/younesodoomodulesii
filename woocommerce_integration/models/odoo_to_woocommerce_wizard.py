from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class OdooToWooCommerceWizard(models.TransientModel):
    _name = 'odoo.to.woocommerce.wizard'
    _description = 'Import Odoo Products to WooCommerce'

    connection_id = fields.Many2one(
        'woocommerce.connection',
        string='WooCommerce Connection',
        required=True,
        help='Select the WooCommerce store to import products to'
    )
    
    import_limit = fields.Integer(
        string='Import Limit',
        default=50,
        help='Maximum number of products to import (0 = no limit)'
    )
    
    batch_size = fields.Integer(
        string='Batch Size',
        default=10,
        help='Number of products to process in each batch (recommended: 10-50)'
    )
    
    include_images = fields.Boolean(
        string='Include Product Images',
        default=True,
        help='Include product images in the import'
    )
    
    overwrite_existing = fields.Boolean(
        string='Overwrite Existing',
        default=False,
        help='Update existing products if they already exist in WooCommerce'
    )
    
    product_domain = fields.Char(
        string='Product Filter',
        default="[('sale_ok', '=', True)]",
        help='Domain to filter products for import'
    )
    
    selected_product_ids = fields.Many2many(
        'product.template',
        string='Selected Products',
        help='Specific products to import (leave empty to import based on filter)'
    )
    
    total_products = fields.Integer(
        string='Total Products',
        readonly=True,
        default=0,
        help='Total number of products to import'
    )
    
    progress_percentage = fields.Float(
        string='Progress',
        readonly=True,
        default=0.0,
        help='Import progress percentage'
    )
    
    import_status = fields.Selection([
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('error', 'Error'),
    ], string='Import Status', default='draft', readonly=True)
    
    import_log = fields.Text(
        string='Import Log',
        readonly=True,
        help='Detailed log of the import process'
    )
    
    imported_count = fields.Integer(
        string='Imported Count',
        readonly=True,
        default=0
    )
    
    error_count = fields.Integer(
        string='Error Count',
        readonly=True,
        default=0
    )
    
    @api.model
    def default_get(self, fields_list):
        """Set default values"""
        res = super().default_get(fields_list)
        
        # Get the first active connection as default
        connection = self.env['woocommerce.connection'].search([
            ('active', '=', True),
            ('connection_status', '=', 'success')
        ], limit=1)
        
        if connection:
            res['connection_id'] = connection.id
            
        return res
    
    def action_test_connection(self):
        """Test the WooCommerce connection"""
        self.ensure_one()
        
        if not self.connection_id:
            raise UserError(_('Please select a WooCommerce connection first.'))
        
        return self.connection_id.test_connection()
    
    def action_import_products(self):
        """Start importing products from Odoo to WooCommerce with batch processing"""
        self.ensure_one()
        
        if not self.connection_id:
            raise UserError(_('Please select a WooCommerce connection first.'))
        
        if self.connection_id.connection_status != 'success':
            raise UserError(_('Please test the connection first before importing products.'))
        
        # Get products to import
        if self.selected_product_ids:
            products = self.selected_product_ids
        else:
            domain = eval(self.product_domain) if self.product_domain else [('sale_ok', '=', True)]
            products = self.env['product.template'].search(domain)
            
            if self.import_limit > 0:
                products = products[:self.import_limit]
        
        total_count = len(products)
        if total_count == 0:
            raise UserError(_('No products found to import.'))
        
        # Initialize the import
        self.write({
            'import_status': 'running',
            'import_log': _('Starting import of %d products in batches of %d...\n\n') % (total_count, self.batch_size),
            'imported_count': 0,
            'error_count': 0,
            'total_products': total_count,
            'progress_percentage': 0.0,
        })
        self.env.cr.commit()  # Commit to show initial status
        
        # Process in batches
        imported_count = 0
        error_count = 0
        batch_num = 0
        
        for i in range(0, total_count, self.batch_size):
            batch_num += 1
            batch = products[i:i + self.batch_size]
            batch_start = i + 1
            batch_end = min(i + self.batch_size, total_count)
            
            self.write({
                'import_log': self.import_log + _('--- Batch %d: Processing products %d-%d ---\n') % (batch_num, batch_start, batch_end)
            })
            
            for product in batch:
                try:
                    result = self._import_single_product(product)
                    if result['success']:
                        imported_count += 1
                        self.write({
                            'import_log': self.import_log + _('✅ %s: %s (ID: %d)\n') % (result['action'], product.name, result['wc_id'])
                        })
                    else:
                        error_count += 1
                        self.write({
                            'import_log': self.import_log + _('❌ Error: %s - %s\n') % (product.name, result['error'])
                        })
                        
                except Exception as e:
                    error_count += 1
                    self.write({
                        'import_log': self.import_log + _('❌ Exception: %s - %s\n') % (product.name, str(e))
                    })
                    _logger.error(f"Error importing product {product.name}: {str(e)}")
            
            # Update progress after each batch
            processed = batch_end
            progress = (processed / total_count) * 100
            self.write({
                'imported_count': imported_count,
                'error_count': error_count,
                'progress_percentage': progress,
            })
            self.env.cr.commit()  # Commit after each batch to show progress
            
            _logger.info(f"Batch {batch_num} completed: {imported_count} imported, {error_count} errors, {progress:.1f}% done")
        
        # Update final status
        self.write({
            'import_status': 'completed' if error_count == 0 else 'error',
            'imported_count': imported_count,
            'error_count': error_count,
            'progress_percentage': 100.0,
            'import_log': self.import_log + _('\n=== Import Completed ===\n') + 
                          _('Total: %d products\n') % total_count +
                          _('Imported: %d\n') % imported_count +
                          _('Errors: %d\n') % error_count
        })
        
        # Show notification and return to the wizard to show final results
        self.env['bus.bus']._sendone(
            self.env.user.partner_id,
            'simple_notification',
            {
                'title': _('Import Completed'),
                'message': _('Imported: %d / %d products (%d errors)') % (imported_count, total_count, error_count),
                'type': 'success' if error_count == 0 else 'warning',
                'sticky': True,
            }
        )
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Import Results'),
            'res_model': 'odoo.to.woocommerce.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }
    
    def _import_single_product(self, product):
        """Import a single product to WooCommerce"""
        try:
            # Check if product already exists in WooCommerce
            existing_wc_product = self.env['woocommerce.product'].search([
                ('odoo_product_id', '=', product.id),
                ('connection_id', '=', self.connection_id.id)
            ])
            
            if existing_wc_product and not self.overwrite_existing:
                return {
                    'success': False,
                    'error': 'Product already exists (skipped)',
                    'action': 'Skipped'
                }
            
            # Create or update WooCommerce product record
            wc_product_vals = self._prepare_woocommerce_product_data(product)
            
            if existing_wc_product:
                existing_wc_product.write(wc_product_vals)
                wc_product = existing_wc_product
                action = 'Updated'
            else:
                wc_product = self.env['woocommerce.product'].create(wc_product_vals)
                action = 'Imported'
            
            # Import images if requested
            if self.include_images and product.image_1920:
                self._import_product_image(product, wc_product)
            
            # Push to WooCommerce store
            wc_product._sync_to_woocommerce_store()
            
            return {
                'success': True,
                'action': action,
                'wc_id': wc_product.wc_product_id,
            }
            
        except Exception as e:
            _logger.error(f"Error importing product {product.name}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'action': 'Failed'
            }
    
    def _prepare_woocommerce_product_data(self, product):
        """Prepare WooCommerce product data from Odoo product"""
        return {
            'wc_product_id': 0,  # Will be updated after creation in WooCommerce
            'connection_id': self.connection_id.id,
            'name': product.name,
            'wc_sku': product.default_code or '',
            'price': product.list_price,
            'regular_price': product.list_price,
            'sale_price': 0,  # Will be set if there's a sale price
            'stock_status': 'instock' if product.qty_available > 0 else 'outofstock',
            'status': 'publish' if product.sale_ok else 'draft',
            'featured': False,
            'odoo_product_id': product.id,
            'last_sync': fields.Datetime.now(),
            'sync_status': 'pending',
            'sync_error': False,
        }
    
    def _import_product_image(self, product, wc_product):
        """Import product image to WooCommerce"""
        if not product.image_1920:
            return
        
        # Create WooCommerce product image record
        image_vals = {
            'product_id': wc_product.id,
            'name': product.name,
            'sequence': 5,  # Main image
            'is_main_image': True,
            'image_1920': product.image_1920,
            'alt_text': product.name,
            'sync_status': 'pending',
        }
        
        image_record = self.env['woocommerce.product.image'].create(image_vals)
        
        # Try to sync the image
        try:
            image_record.action_sync_to_woocommerce()
        except Exception as e:
            _logger.error(f"Error syncing image for product {product.name}: {str(e)}")
    
    def action_view_imported_products(self):
        """View imported products"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Imported to WooCommerce Products'),
            'res_model': 'woocommerce.product',
            'view_mode': 'list,form',
            'domain': [('connection_id', '=', self.connection_id.id)],
            'context': {'default_connection_id': self.connection_id.id}
        }
    
    def action_refresh_status(self):
        """Refresh the wizard view to see updated progress"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Import Odoo Products to WooCommerce'),
            'res_model': 'odoo.to.woocommerce.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }
