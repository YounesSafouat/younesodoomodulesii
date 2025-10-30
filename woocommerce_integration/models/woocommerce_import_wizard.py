from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

# WooCommerce Import Wizard for Product Synchronization


class WooCommerceImportWizard(models.TransientModel):
    _name = 'woocommerce.import.wizard'
    _description = 'WooCommerce Import Wizard'

    name = fields.Char(
        string='Import Name',
        default='WooCommerce Import',
        help='Name for this import job'
    )
    
    connection_id = fields.Many2one(
        'woocommerce.connection',
        string='Connection',
        required=True,
        readonly=True
    )
    
    total_products = fields.Integer(
        string='Total Products',
        readonly=True
    )
    
    import_limit = fields.Integer(
        string='Total Products to Import',
        default=50,
        help='Total number of products to import (0 = import all)'
    )
    
    batch_size = fields.Integer(
        string='Products per Batch',
        default=25,
        help='Number of products to import in each batch (max 25 for stability)'
    )
    
    current_batch = fields.Integer(
        string='Current Batch',
        default=1,
        readonly=True
    )
    
    total_batches = fields.Integer(
        string='Total Batches',
        compute='_compute_total_batches',
        store=False
    )
    
    batches_completed = fields.Integer(
        string='Batches Completed',
        default=0,
        readonly=True
    )
    
    @api.depends('import_limit', 'batch_size', 'total_products')
    def _compute_total_batches(self):
        for record in self:
            if record.batch_size > 0:
                total_to_import = record.import_limit if record.import_limit > 0 else record.total_products
                record.total_batches = (total_to_import + record.batch_size - 1) // record.batch_size
            else:
                record.total_batches = 0
    
    @api.onchange('batch_size')
    def _onchange_batch_size(self):
        """Limit batch size to maximum 25"""
        if self.batch_size > 25:
            self.batch_size = 25
            return {
                'warning': {
                    'title': 'Batch Size Limited',
                    'message': 'Batch size is limited to 25 products for stability and to prevent timeouts.'
                }
            }
    
    import_categories = fields.Boolean(
        string='Import Categories',
        default=True,
        help='Import product categories'
    )
    
    import_images = fields.Boolean(
        string='Import Images',
        default=True,
        help='Import product images'
    )
    
    import_attributes = fields.Boolean(
        string='Import Attributes',
        default=True,
        help='Import product attributes'
    )
    
    overwrite_existing = fields.Boolean(
        string='Overwrite Existing',
        default=False,
        help='Completely overwrite existing products (recreate from scratch)'
    )
    
    update_existing = fields.Boolean(
        string='Update if Exists',
        default=True,
        help='Update existing products with new data from WooCommerce instead of skipping them'
    )
    
    process_in_background = fields.Boolean(
        string='Process in Background',
        default=False,
        help='Process import in background using scheduled actions (recommended for large imports to avoid timeouts)'
    )
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('importing', 'Importing'),
        ('done', 'Done'),
    ], default='draft')
    
    # Progress tracking fields
    progress_current = fields.Integer('Current Progress', default=0)
    progress_total = fields.Integer('Total Items', default=0)
    progress_percentage = fields.Float('Progress Percentage', compute='_compute_progress_percentage', store=False)
    progress_message = fields.Char('Progress Message', default='')
    
    @api.depends('progress_current', 'progress_total')
    def _compute_progress_percentage(self):
        for record in self:
            if record.progress_total > 0:
                record.progress_percentage = (record.progress_current / record.progress_total) * 100
            else:
                record.progress_percentage = 0.0
    
    imported_count = fields.Integer(
        string='Imported Count',
        readonly=True
    )
    
    error_count = fields.Integer(
        string='Error Count',
        readonly=True
    )
    
    log_message = fields.Text(
        string='Log Message',
        readonly=True
    )

    @api.model
    def default_get(self, fields_list):
        """Set default values"""
        defaults = super().default_get(fields_list)
        
        if 'connection_id' in self.env.context:
            connection_id = self.env.context['connection_id']
            connection = self.env['woocommerce.connection'].browse(connection_id)
            if connection.exists():
                defaults['connection_id'] = connection_id
                defaults['total_products'] = connection.total_products
        
        return defaults

    def action_start_import(self):
        """Start the import process - first batch"""
        self.ensure_one()
        
        if not self.connection_id:
            raise UserError(_('Please select a WooCommerce connection.'))
        
        # Validate batch size
        if self.batch_size > 25:
            raise UserError(_('Batch size cannot exceed 25 products for stability.'))
        
        # Background processing is now always used to prevent timeouts
        # Start the background import
        self._start_background_import_logic()
        
        # Close wizard and show notification with progress
        import_limit = self.import_limit or self.total_products
        batches = self.total_batches
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Import Started Successfully'),
                'message': _('✅ Product import is running in the background!\n\n📦 Processing: %d products\n📊 Batches: %d batches\n⏱️ Estimated time: ~%d minutes\n\nYou can check progress in the WooCommerce Connections page.') % (import_limit, batches, batches),
                'type': 'success',
                'sticky': True,
            }
        }
    
    def action_process_next_batch(self):
        """Process the next batch of products"""
        self.ensure_one()
        
        if self.state != 'importing':
            raise UserError(_('Import is not in progress.'))
        
        # Check if all batches are completed
        if self.batches_completed >= self.total_batches:
            self.write({
                'state': 'done',
                'log_message': str(self.log_message or '') + _('\n🎉 All batches completed!'),
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Import Completed'),
                    'message': _('Successfully imported all products!'),
                    'type': 'success',
                    'sticky': True,
                }
            }
        
        try:
            # Process next batch
            self._import_single_batch()
            
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'woocommerce.import.wizard',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
            }
            
        except Exception as e:
            error_message = str(e)
            self.write({
                'error_count': self.error_count + 1,
                'log_message': str(self.log_message or '') + _('\n❌ Batch %d failed: %s') % (self.current_batch, error_message),
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Batch Failed'),
                    'message': _('Failed to process batch %d: %s') % (self.current_batch, error_message),
                    'type': 'warning',
                    'sticky': True,
                }
            }
    
    def _start_background_import_logic(self):
        """Start import in background using scheduled action"""
        self.ensure_one()
        
        # Initialize progress on connection record (persisted, not transient)
        total_to_import = self.import_limit if self.import_limit > 0 else self.total_products
        self.connection_id.write({
            'import_in_progress_persisted': True,
            'import_progress_count_persisted': 0,
            'import_total_count_persisted': total_to_import,
        })
        self.env.cr.commit()
        
        # First, update the state
        try:
            self.write({
                'state': 'importing',
                'imported_count': 0,
                'error_count': 0,
                'current_batch': 1,
                'batches_completed': 0,
                'log_message': _('Starting background import...\n'),
            })
            # Flush to commit the state change
            self.env.cr.commit()
        except Exception as e:
            _logger.error(f'Error updating wizard state: {e}')
        
        # Create or update a scheduled action for this import
        cron_name = f'WooCommerce Import - {self.name}'
        
        try:
            # Search for existing cron
            existing_cron = self.env['ir.cron'].sudo().search([
                ('name', '=', cron_name)
            ], limit=1)
            
            if existing_cron:
                existing_cron.unlink()
            
            # Get model ID
            model_id = self.env['ir.model'].sudo().search([('model', '=', 'woocommerce.import.wizard')], limit=1).id
            
            # Create new scheduled action
            cron = self.env['ir.cron'].sudo().create({
                'name': cron_name,
                'model_id': model_id,
                'state': 'code',
                'code': f'env["woocommerce.import.wizard"].browse({self.id})._import_single_batch_in_background()',
                'interval_number': 1,
                'interval_type': 'minutes',
                'active': True,
                'user_id': self.env.uid,
            })
            
            _logger.info(f'Cron job {cron_name} created successfully')
            
        except Exception as e:
            _logger.error(f'Error creating cron job: {e}')
            # Fallback: run first batch directly
            self._import_single_batch()
    
    def _start_background_import(self):
        """Legacy method - kept for compatibility"""
        return self._start_background_import_logic()
    
    def _import_single_batch_in_background(self):
        """Process single batch in background"""
        self.ensure_one()
        
        try:
            # Check if import is complete
            if self.batches_completed >= self.total_batches:
                # Reset import state on connection
                self.connection_id.write({
                    'import_in_progress_persisted': False,
                })
                self.env.cr.commit()
                
                # Mark as done and unlink cron
                self.write({
                    'state': 'done',
                    'log_message': str(self.log_message or '') + _('\n🎉 All batches completed!'),
                })
                self.env.cr.commit()
                
                # Clean up cron
                cron_name = f'WooCommerce Import - {self.name}'
                cron = self.env['ir.cron'].sudo().search([('name', '=', cron_name)], limit=1)
                if cron:
                    cron.sudo().unlink()
                self.env.cr.commit()
                
                # Send success notification to user
                try:
                    # Create a notification
                    self.env['bus.bus']._sendone(
                        self.env.user.partner_id,
                        'simple_notification',
                        {
                            'title': _('✅ Product Import Completed'),
                            'message': _('Successfully imported %d products from WooCommerce!') % self.imported_count,
                            'type': 'success',
                            'sticky': True,
                        }
                    )
                except Exception as e:
                    _logger.warning(f'Could not send notification: {e}')
                
                _logger.info(f'Import completed: {self.imported_count} products imported')
                
                return
            
            # Process current batch
            self._import_single_batch()
            
            # Update progress on connection record (persisted, not transient)
            self.connection_id.write({
                'import_progress_count_persisted': self.imported_count,
                'import_total_count_persisted': self.import_limit if self.import_limit > 0 else self.total_products,
            })
            self.env.cr.commit()
            
            # Update batch count (for logging)
            self.write({
                'batches_completed': self.batches_completed + 1,
                'current_batch': self.current_batch + 1,
            })
            self.env.cr.commit()
            
        except Exception as e:
            _logger.error(f'Error in background import batch: {str(e)}')
            self.write({
                'error_count': self.error_count + 1,
                'log_message': str(self.log_message or '') + _('\n❌ Batch %d failed: %s') % (self.current_batch, str(e)),
            })
            self.env.cr.commit()

    def _import_products_simple(self):
        """Simplified import process to avoid complex transaction issues"""
        self.ensure_one()
        
        try:
            imported_count = 0
            error_count = 0
            log_messages = []
            page = 1
            batch_size = 20
            max_products = self.import_limit if self.import_limit > 0 else 100
            
            log_messages.append(_('🚀 Starting batch import...'))
            
            while imported_count + error_count < max_products:
                products_data = self.connection_id.get_products(
                    page=page,
                    per_page=batch_size
                )
                
                if not products_data:
                    break
                
                log_messages.append(_('📦 Processing batch %d (%d products)...') % (page, len(products_data)))
                
                for product_data in products_data:
                    try:
                        existing = self.env['woocommerce.product'].search([
                            ('wc_product_id', '=', product_data.get('id')),
                            ('connection_id', '=', self.connection_id.id)
                        ])
                        
                        # Handle existing products based on user preferences
                        if existing:
                            if self.overwrite_existing:
                                # Delete and recreate the product
                                if existing.odoo_product_id:
                                    existing.odoo_product_id.with_context(skip_wc_sync=True).unlink()
                                existing.with_context(skip_wc_sync=True).unlink()
                                log_messages.append(_('🔄 Overwriting: %s') % product_data.get('name', ''))
                            elif self.update_existing:
                                # Update the existing product
                                self._update_existing_product(existing, product_data)
                                imported_count += 1
                                log_messages.append(_('🔄 Updated: %s') % product_data.get('name', ''))
                                continue
                            else:
                                # Skip the product
                                log_messages.append(_('⏭️  Skipping: %s (already exists)') % product_data.get('name', ''))
                                continue
                        
                        product_vals = {
                            'name': product_data.get('name', 'Imported Product'),
                            'list_price': float(product_data.get('price', product_data.get('regular_price', 0)) or 0),
                            'default_code': product_data.get('sku', ''),
                            'description': product_data.get('description', ''),
                            'description_sale': product_data.get('short_description', ''),
                            'sale_ok': product_data.get('status') == 'publish',
                            'purchase_ok': True,
                            'wc_product_id': product_data.get('id'),
                            'wc_connection_id': self.connection_id.id,
                            'wc_sync_enabled': True,
                            'wc_sync_direction': 'wc_to_odoo',
                            'wc_sync_status': 'synced',
                            'wc_last_sync': fields.Datetime.now(),
                            'wc_auto_sync': True,
                            'wc_image_sync_enabled': self.import_images,
                        }
                        
                        odoo_product = self.env['product.template'].with_context(
                            importing_from_woocommerce=True,
                            skip_wc_sync=True
                        ).create(product_vals)
                        
                        wc_product_vals = {
                            'wc_product_id': product_data.get('id'),
                            'connection_id': self.connection_id.id,
                            'name': product_data.get('name', ''),
                            'wc_sku': product_data.get('sku', ''),
                            'price': float(product_data.get('price', 0)),
                            'regular_price': float(product_data.get('regular_price', 0)),
                            'sale_price': float(product_data.get('sale_price', 0)) if product_data.get('sale_price') else 0,
                            'stock_status': product_data.get('stock_status', 'instock'),
                            'status': product_data.get('status', 'publish'),
                            'featured': product_data.get('featured', False),
                            'categories': str(product_data.get('categories', [])),
                            'images': str(product_data.get('images', [])),
                            'attributes': str(product_data.get('attributes', [])),
                            'wc_data': str(product_data),
                            'odoo_product_id': odoo_product.id,
                            'last_sync': fields.Datetime.now(),
                            'sync_status': 'synced',
                            'sync_error': False,
                        }
                        
                        if existing:
                            # Prevent sync back to WooCommerce during import
                            existing.with_context(importing_from_woocommerce=True).write(wc_product_vals)
                            wc_product = existing
                        else:
                            # Prevent sync back to WooCommerce during import
                            wc_product = self.env['woocommerce.product'].with_context(importing_from_woocommerce=True).create(wc_product_vals)
                        
                        # Map categories if they exist
                        if product_data.get('categories'):
                            self._map_product_categories(wc_product, product_data.get('categories'))
                        
                        if self.import_images and product_data.get('images'):
                            for idx, image_data in enumerate(product_data.get('images', [])):
                                try:
                                    image_data['sequence'] = (idx + 1) * 10
                                    self.env['woocommerce.product.image'].create_from_woocommerce_data(
                                        image_data, wc_product.id
                                    )
                                except Exception as e:
                                    _logger.error(f"Error importing image: {e}")
                                    continue
                        
                        imported_count += 1
                        log_messages.append(_('✅ Created product: %s') % product_data.get('name', ''))
                        
                    except Exception as e:
                        error_count += 1
                        log_messages.append(_('❌ Error creating product %s: %s') % (
                            product_data.get('name', ''), str(e)
                        ))
                        _logger.error(f"Error creating product {product_data.get('name')}: {e}")
                
                page += 1
                
                if page % 3 == 0:
                    self.write({
                        'imported_count': imported_count,
                        'error_count': error_count,
                        'log_message': '\n'.join(log_messages[-10:]),
                    })
            
            self.write({
                'imported_count': imported_count,
                'error_count': error_count,
                'log_message': '\n'.join(log_messages),
            })
            
        except Exception as e:
            _logger.error(f"Error in simplified import: {e}")
            self.write({
                'error_count': self.error_count + 1,
                'log_message': str(self.log_message or '') + _('\n❌ Import error: %s') % str(e),
            })
            raise

    def _import_single_batch(self):
        """Import a single batch of products"""
        self.ensure_one()
        
        # Calculate which products to fetch for this batch
        start_index = (self.current_batch - 1) * self.batch_size
        total_to_import = self.import_limit if self.import_limit > 0 else self.total_products
        remaining = total_to_import - self.imported_count
        
        if remaining <= 0:
            self.write({
                'state': 'done',
                'log_message': str(self.log_message or '') + _('\n✅ All products imported!'),
            })
            return
        
        # Determine batch size for this iteration
        current_batch_size = min(self.batch_size, remaining)
        
        # Calculate WooCommerce API page and per_page parameters
        wc_page = (self.imported_count // current_batch_size) + 1
        
        self.write({
            'progress_message': f'Processing batch {self.current_batch} of {self.total_batches}...',
            'progress_total': current_batch_size,
            'progress_current': 0,
        })
        
        try:
            # Fetch products from WooCommerce
            _logger.info(f"Fetching batch {self.current_batch}: page={wc_page}, per_page={current_batch_size}")
            
            products_data = self.connection_id.get_products(
                page=wc_page,
                per_page=current_batch_size
            )
            
            if not products_data:
                self.write({
                    'log_message': str(self.log_message or '') + _('\n⚠️ No more products found.'),
                    'state': 'done',
                })
                return
            
            # Process each product in this batch
            batch_imported = 0
            batch_errors = 0
            
            for idx, product_data in enumerate(products_data):
                try:
                    self.progress_message = f"Batch {self.current_batch}/{self.total_batches}: Importing {product_data.get('name', 'Unknown')[:30]}..."
                    self.progress_current = idx + 1
                    
                    # Check if product already exists
                    existing_wc_product = self.env['woocommerce.product'].search([
                        ('wc_product_id', '=', product_data.get('id')),
                        ('connection_id', '=', self.connection_id.id)
                    ])
                    
                    # Handle existing products based on user preferences
                    if existing_wc_product:
                        if self.overwrite_existing:
                            # Delete and recreate the product
                            if existing_wc_product.odoo_product_id:
                                existing_wc_product.odoo_product_id.with_context(skip_wc_sync=True).unlink()
                            existing_wc_product.with_context(skip_wc_sync=True).unlink()
                            self.log_message = str(self.log_message or '') + _('\n🔄 Overwriting: %s') % product_data.get('name', '')
                        elif self.update_existing:
                            # Update the existing product
                            self._update_existing_product(existing_wc_product, product_data)
                            batch_imported += 1
                            self.log_message = str(self.log_message or '') + _('\n🔄 Updated: %s') % product_data.get('name', '')
                            continue
                        else:
                            # Skip the product
                            self.log_message = str(self.log_message or '') + _('\n⏭️  Skipping: %s (already exists)') % product_data.get('name', '')
                            continue
                    
                    # Create Odoo product
                    product_vals = {
                        'name': product_data.get('name', 'Imported Product'),
                        'list_price': float(product_data.get('price', product_data.get('regular_price', 0)) or 0),
                        'default_code': product_data.get('sku', ''),
                        'description': product_data.get('description', ''),
                        'description_sale': product_data.get('short_description', ''),
                        'sale_ok': product_data.get('status') == 'publish',
                        'purchase_ok': True,
                        'wc_product_id': product_data.get('id'),
                        'wc_connection_id': self.connection_id.id,
                        'wc_sync_enabled': False,  # Disable sync during import to prevent loops
                        'wc_sync_direction': 'wc_to_odoo',
                        'wc_sync_status': 'synced',
                        'wc_last_sync': fields.Datetime.now(),
                        'wc_auto_sync': False,  # Disable auto-sync during import
                        'wc_image_sync_enabled': self.import_images,
                    }
                    
                    odoo_product = self.env['product.template'].with_context(
                        importing_from_woocommerce=True,
                        skip_wc_sync=True
                    ).create(product_vals)
                    
                    # Process custom attributes using field mappings
                    self._process_product_attributes(odoo_product, product_data)
                    
                    # Create WooCommerce product record
                    wc_product_vals = {
                        'wc_product_id': product_data.get('id'),
                        'connection_id': self.connection_id.id,
                        'name': product_data.get('name', ''),
                        'wc_sku': product_data.get('sku', ''),
                        'price': float(product_data.get('price', 0)),
                        'regular_price': float(product_data.get('regular_price', 0)),
                        'sale_price': float(product_data.get('sale_price', 0)) if product_data.get('sale_price') else 0,
                        'stock_status': product_data.get('stock_status', 'instock'),
                        'status': product_data.get('status', 'publish'),
                        'featured': product_data.get('featured', False),
                        'categories': str(product_data.get('categories', [])),
                        'images': str(product_data.get('images', [])),
                        'attributes': str(product_data.get('attributes', [])),
                        'wc_data': str(product_data),
                        'odoo_product_id': odoo_product.id,
                        'last_sync': fields.Datetime.now(),
                        'sync_status': 'synced',
                    }
                    
                    wc_product = self.env['woocommerce.product'].with_context(
                        skip_wc_sync=True
                    ).create(wc_product_vals)
                    
                    # Import images if requested
                    if self.import_images and product_data.get('images'):
                        for image_data in product_data.get('images', []):
                            try:
                                self.env['woocommerce.product.image'].with_context(
                                    importing_from_woocommerce=True
                                ).create_from_woocommerce_data(
                                    image_data, wc_product.id
                                )
                            except Exception as e:
                                _logger.error(f"Error importing image: {e}")
                    
                    batch_imported += 1
                    self.log_message = str(self.log_message or '') + _('\n✅ Imported: %s') % product_data.get('name', '')
                    
                except Exception as e:
                    batch_errors += 1
                    error_msg = _('\n❌ Failed: %s - %s') % (product_data.get('name', 'Unknown'), str(e))
                    self.log_message = str(self.log_message or '') + error_msg
                    _logger.error(f"Error importing product: {e}")
            
            # Update wizard state after batch completion
            self.write({
                'imported_count': self.imported_count + batch_imported,
                'error_count': self.error_count + batch_errors,
                'batches_completed': self.batches_completed + 1,
                'current_batch': self.current_batch + 1,
                'progress_message': f'Batch {self.batches_completed + 1} completed! ({batch_imported} imported, {batch_errors} errors)',
                'log_message': str(self.log_message or '') + _('\n\n📦 Batch %d/%d completed: %d imported, %d errors\n') % (
                    self.batches_completed + 1, self.total_batches, batch_imported, batch_errors
                ),
            })
            
            # Check if all batches are done
            if self.batches_completed >= self.total_batches:
                self.write({
                    'state': 'done',
                    'progress_message': f'All batches completed! Total: {self.imported_count} imported, {self.error_count} errors',
                })
            
        except Exception as e:
            _logger.error(f"Error during batch import: {e}")
            error_message = str(e) if e else 'Unknown error occurred'
            
            self.write({
                'state': 'draft',
                'error_count': self.error_count + 1,
                'log_message': str(self.log_message or '') + _('\n❌ Import failed: %s') % error_message,
            })
            raise

    def _import_products(self):
        """Import products from WooCommerce"""
        self.ensure_one()
        
        page = 1
        per_page = min(100, self.import_limit or 100)
        imported = 0
        
        with self.env.registry.cursor() as new_cr:
            new_env = api.Environment(new_cr, self.env.uid, self.env.context)
            wizard_record = new_env['woocommerce.import.wizard'].browse(self.id)
            
            if not wizard_record.log_message:
                wizard_record.log_message = ""
            
            try:
                while True:
                    if self.import_limit and imported >= self.import_limit:
                        break
                    
                    batch_size = per_page
                    if self.import_limit:
                        remaining = self.import_limit - imported
                        batch_size = min(batch_size, remaining)
                    
                    try:
                        products_data = self.connection_id.get_products(
                            page=page,
                            per_page=batch_size
                        )
                        
                        if not products_data:
                            break
                        
                        for product_data in products_data:
                            if self.import_limit and imported >= self.import_limit:
                                break
                            
                            try:
                                with new_env.registry.cursor() as product_cr:
                                    product_env = api.Environment(product_cr, self.env.uid, self.env.context)
                                    
                                    existing = product_env['woocommerce.product'].search([
                                        ('wc_product_id', '=', product_data.get('id')),
                                        ('connection_id', '=', self.connection_id.id)
                                    ])
                                    
                                    if existing and not self.overwrite_existing:
                                        wizard_record.log_message = str(wizard_record.log_message or '') + _('Skipping existing product: %s\n') % product_data.get('name', '')
                                        continue
                                    
                                    odoo_product = self._create_or_update_odoo_product_with_env(product_data, existing, product_env)
                                    
                                    if odoo_product:
                                        wizard_record.log_message = str(wizard_record.log_message or '') + _('✅ Created/Updated Odoo product: %s\n') % product_data.get('name', '')
                                        wizard_record.imported_count += 1
                                    else:
                                        wizard_record.log_message = str(wizard_record.log_message or '') + _('⚠️ Skipped product: %s\n') % product_data.get('name', '')
                                    
                                    imported += 1
                                    wizard_record.imported_count = imported
                                    product_cr.commit()
                                    
                            except Exception as e:
                                _logger.error(f"Error importing product {product_data.get('id', 'unknown')}: {e}")
                                wizard_record.error_count += 1
                                wizard_record.log_message = str(wizard_record.log_message or '') + _('❌ Error importing product %s: %s\n') % (
                                    product_data.get('name', ''), str(e)
                                )
                                if 'product_cr' in locals():
                                    product_cr.commit()
                        
                        if len(products_data) < batch_size:
                            break
                        
                        page += 1
                        
                    except Exception as e:
                        _logger.error(f"Error fetching products page {page}: {e}")
                        wizard_record.error_count += 1
                        wizard_record.log_message = str(wizard_record.log_message or '') + _('❌ Error fetching page %d: %s\n') % (page, str(e))
                        break
                
                # Update the original record with final counts
                self.write({
                    'imported_count': wizard_record.imported_count,
                    'error_count': wizard_record.error_count,
                    'log_message': wizard_record.log_message,
                })
                new_cr.commit()
                
            except Exception as e:
                _logger.error(f"Critical error during import: {e}")
                new_cr.rollback()
                # Update error count even on critical failure
                self.write({
                    'error_count': self.error_count + 1,
                    'log_message': str(self.log_message or '') + _('\n❌ Critical import error: %s') % str(e),
                })
                raise

    def _create_or_update_odoo_product_with_env(self, wc_data, existing_wc_product=None, env=None):
        """Create or update Odoo product from WooCommerce data with specific environment"""
        if env is None:
            env = self.env
            
        try:
            # Check if Odoo product already exists
            odoo_product = None
            if existing_wc_product and existing_wc_product.odoo_product_id:
                odoo_product = existing_wc_product.odoo_product_id
            
            # Prepare product data for Odoo (simplified to avoid transaction issues)
            product_vals = {
                'name': wc_data.get('name', 'Imported Product'),
                'list_price': float(wc_data.get('price', wc_data.get('regular_price', 0)) or 0),
                'default_code': wc_data.get('sku', ''),
                'description': wc_data.get('description', ''),
                'description_sale': wc_data.get('short_description', ''),
                'sale_ok': wc_data.get('status') == 'publish',
                'purchase_ok': True,
                'wc_product_id': wc_data.get('id'),
                'wc_connection_id': self.connection_id.id,
                'wc_sync_enabled': True,
                'wc_sync_direction': 'wc_to_odoo',
                'wc_sync_status': 'synced',
                'wc_last_sync': fields.Datetime.now(),
                'wc_auto_sync': True,
                'wc_image_sync_enabled': self.import_images,
            }
            
            # Handle categories
            if self.import_categories and wc_data.get('categories'):
                category_id = self._get_or_create_category_with_env(wc_data['categories'], env)
                if category_id:
                    product_vals['categ_id'] = category_id
            
            # Handle images (simplified to avoid download issues)
            if self.import_images and wc_data.get('images'):
                image_url = wc_data['images'][0].get('src') if wc_data['images'] else None
                if image_url:
                    try:
                        # Download and set product image
                        product_vals['image_1920'] = self._download_image(image_url)
                    except Exception as e:
                        _logger.warning(f"Failed to download image for product {wc_data.get('name')}: {e}")
                        # Continue without image
            
            # Create or update Odoo product
            if odoo_product:
                # Update existing product
                odoo_product.write(product_vals)
                _logger.info(f"Updated Odoo product: {odoo_product.name}")
            else:
                # Create new product
                odoo_product = env['product.template'].create(product_vals)
                _logger.info(f"Created Odoo product: {odoo_product.name}")
            
            # Create or update WooCommerce product record
            wc_product_vals = {
                'wc_product_id': wc_data.get('id'),
                'connection_id': self.connection_id.id,
                'name': wc_data.get('name', ''),
                'wc_sku': wc_data.get('sku', ''),
                'price': float(wc_data.get('price', 0)),
                'regular_price': float(wc_data.get('regular_price', 0)),
                'sale_price': float(wc_data.get('sale_price', 0)) if wc_data.get('sale_price') else 0,
                'stock_status': wc_data.get('stock_status', 'instock'),
                'status': wc_data.get('status', 'publish'),
                'featured': wc_data.get('featured', False),
                'categories': str(wc_data.get('categories', [])),
                'images': str(wc_data.get('images', [])),
                'attributes': str(wc_data.get('attributes', [])),
                'wc_data': str(wc_data),
                'odoo_product_id': odoo_product.id,
                'last_sync': fields.Datetime.now(),
                'sync_status': 'synced',
                'sync_error': False,
            }
            
            if existing_wc_product:
                # Prevent sync back to WooCommerce during import
                existing_wc_product.with_context(importing_from_woocommerce=True).write(wc_product_vals)
            else:
                # Prevent sync back to WooCommerce during import
                env['woocommerce.product'].with_context(importing_from_woocommerce=True).create(wc_product_vals)
            
            return odoo_product
            
        except Exception as e:
            _logger.error(f"Error creating/updating Odoo product for {wc_data.get('name')}: {e}")
            return None
    
    def _create_or_update_odoo_product(self, wc_data, existing_wc_product=None):
        """Create or update Odoo product from WooCommerce data (legacy method)"""
        return self._create_or_update_odoo_product_with_env(wc_data, existing_wc_product, self.env)
    
    def _get_or_create_category_with_env(self, wc_categories, env=None):
        """Get or create Odoo category from WooCommerce categories with specific environment"""
        if env is None:
            env = self.env
            
        if not wc_categories:
            return False
        
        try:
            # Use the first category
            wc_category = wc_categories[0]
            category_name = wc_category.get('name', 'Imported Category')
            
            # Check if category already exists
            existing_category = env['product.category'].search([
                ('name', '=', category_name)
            ], limit=1)
            
            if existing_category:
                return existing_category.id
            
            # Create new category
            new_category = env['product.category'].create({
                'name': category_name,
                'parent_id': False,  # Root category
            })
            
            return new_category.id
            
        except Exception as e:
            _logger.warning(f"Error creating category: {e}")
            return False
    
    def _get_or_create_category(self, wc_categories):
        """Get or create Odoo category from WooCommerce categories (legacy method)"""
        return self._get_or_create_category_with_env(wc_categories, self.env)
    
    def _download_image(self, image_url):
        """Download image from URL and return as base64"""
        try:
            import requests
            import base64
            
            response = requests.get(image_url, timeout=600)  # 10 minutes
            response.raise_for_status()
            
            # Convert to base64
            image_data = base64.b64encode(response.content).decode('utf-8')
            return image_data
            
        except Exception as e:
            _logger.warning(f"Error downloading image from {image_url}: {e}")
            raise

    def action_view_imported_products(self):
        """View imported products"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Imported WooCommerce Products'),
            'res_model': 'woocommerce.product',
            'view_mode': 'list,form',
            'domain': [('connection_id', '=', self.connection_id.id)],
            'context': {'default_connection_id': self.connection_id.id}
        }
    
    def _map_product_categories(self, wc_product, categories_data):
        """Map WooCommerce categories to the product"""
        if not categories_data:
            return
        
        category_ids = []
        for cat_data in categories_data:
            if isinstance(cat_data, dict) and cat_data.get('id'):
                # Find existing WooCommerce category by ID
                wc_category = self.env['woocommerce.category'].search([
                    ('wc_category_id', '=', cat_data['id']),
                    ('connection_id', '=', wc_product.connection_id.id)
                ], limit=1)
                
                if wc_category:
                    category_ids.append(wc_category.id)
                else:
                    # Create the category if it doesn't exist
                    wc_category = self.env['woocommerce.category'].create({
                        'wc_category_id': cat_data['id'],
                        'connection_id': wc_product.connection_id.id,
                        'name': cat_data.get('name', 'Imported Category'),
                        'wc_slug': cat_data.get('slug', ''),
                        'sync_status': 'synced',
                        'last_sync': fields.Datetime.now(),
                    })
                    category_ids.append(wc_category.id)
        
        if category_ids:
            wc_product.write({'category_ids': [(6, 0, category_ids)]})
    
    def _update_existing_product(self, wc_product, product_data):
        """Update an existing product with new data from WooCommerce"""
        try:
            # Get the linked Odoo product
            odoo_product = wc_product.odoo_product_id
            
            if not odoo_product:
                _logger.warning(f"WooCommerce product {wc_product.wc_product_id} has no linked Odoo product")
                return
            
            # Prepare update values for Odoo product
            update_vals = {
                'name': product_data.get('name', odoo_product.name),
                'list_price': float(product_data.get('price', product_data.get('regular_price', 0)) or 0),
                'default_code': product_data.get('sku', odoo_product.default_code),
                'description': product_data.get('description', odoo_product.description),
                'description_sale': product_data.get('short_description', odoo_product.description_sale),
                'sale_ok': product_data.get('status') == 'publish',
                'wc_last_sync': fields.Datetime.now(),
                'wc_sync_status': 'synced',
            }
            
            # Update Odoo product
            odoo_product.with_context(
                importing_from_woocommerce=True,
                skip_wc_sync=True
            ).write(update_vals)
            
            # Process custom attributes using field mappings
            self._process_product_attributes(odoo_product, product_data)
            
            # Update WooCommerce product record
            wc_update_vals = {
                'name': product_data.get('name', ''),
                'wc_sku': product_data.get('sku', ''),
                'price': float(product_data.get('price', 0)),
                'regular_price': float(product_data.get('regular_price', 0)),
                'sale_price': float(product_data.get('sale_price', 0)) if product_data.get('sale_price') else 0,
                'stock_status': product_data.get('stock_status', 'instock'),
                'status': product_data.get('status', 'publish'),
                'featured': product_data.get('featured', False),
                'categories': str(product_data.get('categories', [])),
                'images': str(product_data.get('images', [])),
                'attributes': str(product_data.get('attributes', [])),
                'wc_data': str(product_data),
                'last_sync': fields.Datetime.now(),
                'sync_status': 'synced',
            }
            
            wc_product.with_context(skip_wc_sync=True).write(wc_update_vals)
            
            # Update images if requested
            if self.import_images and product_data.get('images'):
                # Don't delete existing images - just update them
                # This prevents losing images that were already synced
                
                # Import new images
                for image_data in product_data.get('images', []):
                    try:
                        self.env['woocommerce.product.image'].create_from_woocommerce_data(
                            image_data, wc_product.id
                        )
                    except Exception as e:
                        _logger.error(f"Error importing image: {e}")
            
            _logger.info(f"Successfully updated product: {odoo_product.name}")
            
        except Exception as e:
            _logger.error(f"Error updating existing product: {e}")
            raise
    
    def _process_product_attributes(self, odoo_product, wc_product_data):
        """Process WooCommerce product attributes using field mappings"""
        try:
            # Get active field mappings for this connection
            mappings = self.env['woocommerce.field.mapping'].search([
                ('connection_id', '=', self.connection_id.id),
                ('is_active', '=', True),
                ('mapping_direction', 'in', ['wc_to_odoo', 'bidirectional'])
            ])
            
            if not mappings:
                _logger.info(f"No active field mappings found for connection {self.connection_id.name}")
                return
            
            # Get WooCommerce attributes from product data
            wc_attributes = wc_product_data.get('attributes', [])
            wc_meta_data = wc_product_data.get('meta_data', [])
            
            # Create a lookup dictionary for WooCommerce attributes
            attr_lookup = {}
            for attr in wc_attributes:
                if isinstance(attr, dict) and 'name' in attr and 'options' in attr:
                    # Use both slug and name for lookup
                    attr_lookup[attr.get('slug', '')] = attr
                    attr_lookup[attr.get('name', '')] = attr
            
            # Create a lookup dictionary for meta data
            meta_lookup = {}
            for meta in wc_meta_data:
                if isinstance(meta, dict) and 'key' in meta:
                    meta_lookup[meta['key']] = meta.get('value', '')
            
            # Process each mapping
            update_vals = {}
            for mapping in mappings:
                wc_field = mapping.wc_field_name
                odoo_field = mapping.odoo_field_name
                
                # Skip if Odoo field doesn't exist
                if not hasattr(odoo_product, odoo_field):
                    continue
                
                value = None
                
                # Handle attribute fields
                if wc_field.startswith('attributes.'):
                    attr_key = wc_field.replace('attributes.', '')
                    if attr_key in attr_lookup:
                        attr_data = attr_lookup[attr_key]
                        if wc_field.endswith('.options'):
                            # Get attribute values
                            options = attr_data.get('options', [])
                            value = ', '.join(options) if options else ''
                        else:
                            # Get attribute name or first option
                            options = attr_data.get('options', [])
                            value = options[0] if options else ''
                
                # Handle meta data fields
                elif wc_field.startswith('meta_data.'):
                    meta_key = wc_field.replace('meta_data.', '')
                    value = meta_lookup.get(meta_key, '')
                
                # Handle regular WooCommerce fields
                else:
                    value = wc_product_data.get(wc_field, '')
                
                # Apply transformation if specified
                if value and mapping.transform_function != 'none':
                    value = self._apply_field_transformation(value, mapping)
                
                # Set default value if empty and default is specified
                if not value and mapping.default_value:
                    value = mapping.default_value
                
                # Add to update values if we have a value
                if value is not None:
                    update_vals[odoo_field] = value
            
            # Update the Odoo product with mapped values
            if update_vals:
                _logger.info(f"Attempting to update product {odoo_product.name} with values: {update_vals}")
                
                odoo_product.with_context(
                    importing_from_woocommerce=True,
                    skip_wc_sync=True
                ).write(update_vals)
                
                _logger.info(f"Successfully updated product {odoo_product.name} with {len(update_vals)} mapped attributes")
            
        except Exception as e:
            _logger.error(f"Error processing attributes for product {odoo_product.name}: {e}")
    
    def _apply_field_transformation(self, value, mapping):
        """Apply transformation to field value"""
        try:
            if mapping.transform_function == 'uppercase':
                return str(value).upper()
            elif mapping.transform_function == 'lowercase':
                return str(value).lower()
            elif mapping.transform_function == 'title':
                return str(value).title()
            elif mapping.transform_function == 'trim':
                return str(value).strip()
            elif mapping.transform_function == 'normalize_choice':
                # Special transformation for choice fields with accents
                value_str = str(value).lower()
                # Remove accents and normalize
                import unicodedata
                normalized = unicodedata.normalize('NFD', value_str)
                normalized = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
                return normalized
            elif mapping.transform_function == 'multiply' and mapping.transform_value:
                try:
                    factor = float(mapping.transform_value)
                    return float(value) * factor
                except (ValueError, TypeError):
                    return value
            elif mapping.transform_function == 'divide' and mapping.transform_value:
                try:
                    divisor = float(mapping.transform_value)
                    return float(value) / divisor if divisor != 0 else value
                except (ValueError, TypeError):
                    return value
            elif mapping.transform_function == 'round' and mapping.transform_value:
                try:
                    decimals = int(mapping.transform_value)
                    return round(float(value), decimals)
                except (ValueError, TypeError):
                    return value
            elif mapping.transform_function == 'custom' and mapping.custom_function:
                # Execute custom Python function
                try:
                    exec_globals = {'value': value}
                    exec_locals = {}
                    exec(f"result = {mapping.custom_function}", exec_globals, exec_locals)
                    return exec_locals.get('result', value)
                except Exception as e:
                    _logger.warning(f"Custom transformation failed: {e}")
                    return value
            else:
                return value
        except Exception:
            return value
