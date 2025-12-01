from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import time

_logger = logging.getLogger(__name__)




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
        default=0,
        help='Total number of products to import (0 = import all available products)'
    )
    
    batch_size = fields.Integer(
        string='Products per Batch',
        default=10,
        help='Number of products to import in each batch (smaller batches prevent timeout errors)'
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
        """Limit batch size to maximum 100 (WooCommerce API limit)"""
        if self.batch_size > 100:
            self.batch_size = 100
            return {
                'warning': {
                    'title': 'Batch Size Limited',
                    'message': 'Batch size is limited to 100 products (WooCommerce API maximum).'
                }
            }
    
    import_categories = fields.Boolean(
        string='Import Categories',
        default=True,
        help='Import product categories'
    )
    
    auto_import_categories = fields.Boolean(
        string='Auto-Import All Categories',
        default=True,
        help='Automatically import all WooCommerce categories when importing products. This ensures all product categories are available in Odoo.'
    )
    
    auto_import_coupons = fields.Boolean(
        string='Auto-Import All Coupons',
        default=True,
        help='Automatically import all WooCommerce coupons when importing products. This helps track which products have associated coupons.'
    )
    
    import_images = fields.Boolean(
        string='Import Images',
        default=True,
        help='Import product images'
    )
    
    image_download_mode = fields.Selection([
        ('urls_only', 'Store URLs Only (Faster)'),
        ('download', 'Download Images (Slower)'),
    ], string='Image Download Mode', default='urls_only',
        help='Store only image URLs for faster import, or download images immediately. Images can be downloaded later if needed.'
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


                if defaults.get('import_limit', 0) == 0:
                    defaults['import_limit'] = connection.total_products
        
        return defaults

    def _update_connection_progress(self, imported_count, total_count=None):
        """Update connection progress count - more reliable version
        
        This method updates the connection's progress count after each successful import.
        Non-blocking - will silently fail if database connections are exhausted.
        """
        if not self.connection_id:
            return
        
        progress_cr = None
        try:
            # Try to get a cursor, but don't wait if connections are exhausted
            try:
                progress_cr = self.env.registry.cursor()
            except Exception as cursor_error:
                # If we can't get a cursor (e.g., connection pool exhausted), just skip progress update
                _logger.debug(f"Could not get cursor for progress update (non-critical): {cursor_error}")
                return
            
            try:
                progress_env = self.env(cr=progress_cr)
                connection = progress_env['woocommerce.connection'].browse(self.connection_id.id)
                
                if not connection.exists():
                    return
                
                # Try to lock with NOWAIT to avoid hanging
                try:
                    progress_cr.execute(
                        "SELECT id FROM woocommerce_connection WHERE id = %s FOR UPDATE NOWAIT",
                        (self.connection_id.id,)
                    )
                except Exception as lock_error:
                    # Lock failed, skip this progress update
                    _logger.debug(f"Could not lock connection for progress update (non-critical): {lock_error}")
                    return
                
                update_vals = {
                    'import_progress_count_persisted': imported_count,
                }
                if total_count is not None:
                    update_vals['import_total_count_persisted'] = total_count
                
                connection.sudo().write(update_vals)
                progress_cr.commit()
            except Exception as e:
                if progress_cr and not progress_cr.closed:
                    progress_cr.rollback()
                _logger.debug(f"Error updating connection progress (non-critical): {e}")
        except Exception as e:
            _logger.debug(f"Could not create cursor for progress update (non-critical): {e}")
        finally:
            # Always close the cursor if it was opened
            if progress_cr and not progress_cr.closed:
                try:
                    progress_cr.close()
                except Exception:
                    pass
    
    def _append_to_connection_log(self, message):
        """Append a message to the connection's import log (keeps last 10000 chars)
        
        Simplified version that's more reliable. Uses a separate transaction to avoid
        aborting the main import transaction if there's a concurrency error.
        Non-blocking - will silently fail if database connections are exhausted.
        """
        if not self.connection_id:
            return
        
        if not message:
            return

        log_cr = None
        try:
            # Try to get a cursor, but don't wait if connections are exhausted
            try:
                log_cr = self.env.registry.cursor()
            except Exception as cursor_error:
                # If we can't get a cursor (e.g., connection pool exhausted), just skip logging
                _logger.debug(f"Could not get cursor for log update (non-critical): {cursor_error}")
                return
            
            try:
                log_env = self.env(cr=log_cr)
                connection = log_env['woocommerce.connection'].browse(self.connection_id.id)
                
                if not connection.exists():
                    return
                
                # Simple lock with NOWAIT to avoid hanging
                try:
                    log_cr.execute(
                        "SELECT id FROM woocommerce_connection WHERE id = %s FOR UPDATE NOWAIT",
                        (self.connection_id.id,)
                    )
                except Exception as lock_error:
                    # Lock failed, skip this log update
                    _logger.debug(f"Could not lock connection for log update (non-critical): {lock_error}")
                    return
                
                # Refresh and get current log
                connection.invalidate_recordset(['import_log'])
                connection = log_env['woocommerce.connection'].browse(self.connection_id.id)
                
                current_log = connection.import_log or ''
                new_log = current_log + '\n' + message if current_log else message
                
                # Keep last 10000 chars
                if len(new_log) > 10000:
                    new_log = '...' + new_log[-9997:]

                # Write the log
                connection.sudo().write({'import_log': new_log})
                log_cr.commit()

            except Exception as e:
                if log_cr and not log_cr.closed:
                    log_cr.rollback()
                # Don't log as warning - this is non-critical
                _logger.debug(f"Could not update connection log (non-critical): {e}")
        except Exception as e:
            # Don't log as warning - this is non-critical
            _logger.debug(f"Could not create cursor for log update (non-critical): {e}")
        finally:
            # Always close the cursor if it was opened
            if log_cr and not log_cr.closed:
                try:
                    log_cr.close()
                except Exception:
                    pass
    
    def action_start_import(self):
        """Start the import process - first batch"""
        self.ensure_one()
        _logger.info(f'Starting import for wizard ID {self.id}, connection: {self.connection_id.name if self.connection_id else "None"}')
        


        try:

            self.env.cr.execute("SELECT 1")
        except Exception:

            try:
                if not self.env.cr.closed:
                    self.env.cr.rollback()
            except Exception:
                pass
        
        if not self.connection_id:
            raise UserError(_('Please select a WooCommerce connection.'))
        

        try:
            self.connection_id.sudo().write({'import_log': ''})
            self.env.cr.commit()
        except Exception as e:

            try:
                if not self.env.cr.closed:
                    self.env.cr.rollback()
            except Exception:
                pass
            _logger.warning(f'Error clearing import log: {e}')
        


        try:
            self._start_background_import_logic()
        except Exception as e:

            try:
                if not self.env.cr.closed:
                    self.env.cr.rollback()
            except Exception:
                pass

            raise
        

        import_limit = self.import_limit or self.total_products
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Import Started'),
                'message': _('🚀 Product import is running in the background!\n\n📦 Importing: %d products\n⏱️ This may take several minutes depending on the number of products.\n\n✅ You can continue working while products are imported.\n📊 Check progress in the WooCommerce Connections page.') % import_limit,
                'type': 'success',
                'sticky': True,
            }
        }
    
    def action_process_next_batch(self):
        """Process the next batch of products"""
        self.ensure_one()
        
        if self.state != 'importing':
            raise UserError(_('Import is not in progress.'))
        

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
        _logger.info(f'_start_background_import_logic called for wizard ID {self.id}')
        

        try:

            self.env.cr.execute("SELECT 1")
        except Exception:

            try:
                if not self.env.cr.closed:
                    self.env.cr.rollback()
            except Exception:
                pass
        

        total_to_import = self.import_limit if self.import_limit > 0 else self.total_products
        

        import json
        import_settings = {
            'import_categories': self.import_categories,
            'import_images': self.import_images,
            'import_attributes': self.import_attributes,
            'update_existing': self.update_existing,
            'overwrite_existing': self.overwrite_existing,
        }
        

        start_msg = _('🚀 Import started: %d products will be imported in the background') % total_to_import
        self._append_to_connection_log(start_msg)
        

        max_retries = 3
        retry_count = 0
        connection_updated = False
        
        while retry_count < max_retries and not connection_updated:
            try:

                lock_acquired = False
                try:
                    self.env.cr.execute(
                        "SELECT id FROM woocommerce_connection WHERE id = %s FOR UPDATE NOWAIT",
                        (self.connection_id.id,)
                    )
                    lock_acquired = True
                except Exception as lock_error:

                    self.env.cr.rollback()
                    error_str = str(lock_error).lower()
                    

                    if 'serialize' in error_str or 'concurrent' in error_str or 'lock' in error_str:
                        if retry_count < max_retries - 1:
                            _logger.debug(f"Could not lock connection immediately (attempt {retry_count + 1}/{max_retries}), retrying with wait: {lock_error}")

                            time.sleep(0.3 * (retry_count + 1))

                            try:
                                self.env.cr.execute(
                                    "SELECT id FROM woocommerce_connection WHERE id = %s FOR UPDATE",
                                    (self.connection_id.id,)
                                )
                                lock_acquired = True
                            except Exception as retry_error:

                                self.env.cr.rollback()
                                retry_count += 1
                                if retry_count >= max_retries:
                                    raise UserError(_('Could not start import: Another import process is currently running. Please wait a moment and try again.'))
                                time.sleep(0.5 * retry_count)
                                continue
                        else:
                            raise UserError(_('Could not start import: Another import process is currently running. Please wait a moment and try again.'))
                    else:

                        raise
                
                if not lock_acquired:
                    retry_count += 1
                    if retry_count >= max_retries:
                        raise UserError(_('Could not start import: Unable to acquire lock. Please try again.'))
                    continue
                

                self.connection_id.invalidate_recordset()
                connection = self.env['woocommerce.connection'].browse(self.connection_id.id)
                

                if connection.import_in_progress_persisted:

                    cron_name = f'WooCommerce Import - {connection.name}'
                    cron = self.env['ir.cron'].sudo().search([('name', '=', cron_name)], limit=1)
                    
                    if not cron:

                        _logger.warning(f'Import flag is set but no cron job found for connection {connection.name}. Resetting stuck import flag.')
                        connection.write({
                            'import_in_progress_persisted': False,
                        })
                        self.env.cr.commit()
                    else:

                        self.env.cr.rollback()
                        raise UserError(_('An import is already in progress for this connection. Please wait for it to complete or stop it first.'))
                

                try:
                    connection.write({
                        'import_in_progress_persisted': True,
                        'import_progress_count_persisted': 0,
                        'import_total_count_persisted': total_to_import,
                        'active_import_wizard_id': self.id,
                        'import_batch_size': self.batch_size,
                        'import_settings': json.dumps(import_settings),
                        'import_notification_sent': False,
                    })
                    self.env.cr.commit()
                    connection_updated = True
                except Exception as write_error:

                    self.env.cr.rollback()
                    error_str = str(write_error).lower()
                    if 'serialize' in error_str or 'concurrent' in error_str or 'abort' in error_str:

                        retry_count += 1
                        if retry_count < max_retries:
                            _logger.warning(f'Concurrency error writing connection (attempt {retry_count}/{max_retries}), retrying: {write_error}')
                            time.sleep(0.5 * retry_count)
                            continue
                        else:
                            raise UserError(_('Could not start import due to concurrent access. Please try again in a moment.'))
                    else:
                        raise
                
            except UserError:

                if not self.env.cr.closed:
                    try:
                        self.env.cr.rollback()
                    except Exception:
                        pass
                raise
            except Exception as e:
                retry_count += 1
                error_str = str(e).lower()
                if not self.env.cr.closed:
                    try:
                        self.env.cr.rollback()
                    except Exception:
                        pass
                
                if 'serialize' in error_str or 'concurrent' in error_str:
                    if retry_count < max_retries:
                        _logger.warning(f'Concurrency error updating connection (attempt {retry_count}/{max_retries}), retrying: {e}')
                        time.sleep(0.5 * retry_count)
                    else:
                        raise UserError(_('Could not start import due to concurrent access. Please try again in a moment.'))
                else:

                    raise
        


        try:

            self.env.cr.execute("SELECT 1")
        except Exception:

            try:
                if not self.env.cr.closed:
                    self.env.cr.rollback()
            except Exception:
                pass
        

        try:

            with self.env.registry.cursor() as new_cr:
                new_env = self.env(cr=new_cr)
                wizard = new_env['woocommerce.import.wizard'].browse(self.id)
                wizard.write({
                    'state': 'importing',
                    'imported_count': 0,
                    'error_count': 0,
                    'current_batch': 1,
                    'batches_completed': 0,
                    'log_message': _('Starting background import...\n'),
                })
                new_cr.commit()
        except Exception as e:
            _logger.error(f'Error updating wizard state: {e}')

            try:
                if not self.env.cr.closed:
                    self.env.cr.rollback()
            except Exception:
                pass

        


        cron_name = f'WooCommerce Import - {self.connection_id.name}'
        
        try:

            existing_cron = self.env['ir.cron'].sudo().search([
                ('name', '=', cron_name)
            ], limit=1)
            
            if existing_cron:
                existing_cron.unlink()
            

            model_id = self.env['ir.model'].sudo().search([('model', '=', 'woocommerce.connection')], limit=1).id
            
            if not model_id:
                raise Exception('Could not find woocommerce.connection model')
            

            cron = self.env['ir.cron'].sudo().create({
                'name': cron_name,
                'model_id': model_id,
                'state': 'code',
                'code': f'env["woocommerce.connection"].browse({self.connection_id.id}).process_next_import_batch()',
                'interval_number': 1,
                'interval_type': 'minutes',
                'active': True,
                'user_id': self.env.uid,
            })
            
            # Commit the cron job creation to ensure it persists
            self.env.cr.commit()
            _logger.info(f'Cron job {cron_name} (ID: {cron.id}) created successfully for connection {self.connection_id.name}')
            

            # For large imports, use batch-based approach instead of processing all at once
            # This prevents timeouts and allows the cron job to continue processing
            # Use self instead of wizard since wizard is out of scope after the with block
            total_to_import = self.import_limit if self.import_limit > 0 else self.total_products
            if total_to_import > 20:
                _logger.info(f'Large import detected ({total_to_import} products). Using batch-based approach to avoid timeout.')
                self._append_to_connection_log(_('\n📦 Large import detected. Processing in batches to avoid timeout...'))
                # Process first batch immediately, then let cron handle the rest
                try:
                    self._import_single_batch()
                    _logger.info('First batch processed. Remaining batches will be processed by cron job.')
                except Exception as batch_error:
                    _logger.error(f'Error processing first batch: {batch_error}')
                    self._append_to_connection_log(_('\n❌ Error processing first batch: %s') % str(batch_error))
            else:
                _logger.info('Fetching all products immediately...')
                try:
                    self._import_all_products_immediately()
                    _logger.info('All products fetched and queued for processing')
                except Exception as e:
                    _logger.error(f'Error fetching all products: {e}')

                    try:
                        self._import_single_batch()
                    except Exception as fallback_error:
                        _logger.error(f'Error in fallback batch processing: {fallback_error}')
            
        except Exception as e:
            _logger.error(f'Error creating cron job: {e}')

            self._import_single_batch()
    
    def _start_background_import(self):
        """Legacy method - kept for compatibility"""
        return self._start_background_import_logic()
    
    def _import_single_batch_in_background(self):
        """Process single batch in background"""
        self.ensure_one()
        
        try:

            wizard = self.sudo().exists()
            if not wizard:
                _logger.warning(f'Wizard record {self.id} no longer exists, checking connection for progress')

                connection = self.connection_id.sudo().exists()
                if connection:

                    if not connection.import_in_progress_persisted:
                        _logger.info('Import marked as complete on connection, cleaning up cron')
                        cron_name = f'WooCommerce Import - {connection.name}'
                        cron = self.env['ir.cron'].sudo().search([('name', '=', cron_name)], limit=1)
                        if cron:
                            cron.sudo().unlink()
                        return
                else:
                    _logger.error('Connection record also not found, aborting')
                    return
            


            current_batch = wizard.current_batch
            total_batches = wizard.total_batches
            imported_count = wizard.imported_count
            total_to_import = wizard.import_limit if wizard.import_limit > 0 else wizard.total_products
            


            _logger.info(f'Checking import status: batches {current_batch}/{total_batches}, products {imported_count}/{total_to_import}, import_in_progress={self.connection_id.import_in_progress_persisted}')
            

            if current_batch > total_batches:
                _logger.info(f'Import stopping: exceeded total batches ({current_batch} > {total_batches})')

                self.connection_id.sudo().write({
                    'import_in_progress_persisted': False,
                })
                self.env.cr.commit()
                

                cron_name = f'WooCommerce Import - {self.connection_id.name}'
                cron = self.env['ir.cron'].sudo().search([('name', '=', cron_name)], limit=1)
                if cron:
                    cron.sudo().unlink()
                self.env.cr.commit()
                

                warning_msg = _('\n⚠️ Import stopped: reached maximum batches (%d/%d). %d products imported.') % (
                    current_batch, total_batches, imported_count
                )
                wizard._append_to_connection_log(warning_msg)
                return
            



            if total_to_import > 0 and imported_count >= total_to_import:
                _logger.info(f'Import complete: batches {current_batch}/{total_batches}, products {imported_count}/{total_to_import}')
                

                completion_msg = _('\n🎉 Import completed: %d products imported successfully!') % imported_count
                wizard._append_to_connection_log(completion_msg)
                
                # Auto-import categories and coupons if enabled
                try:
                    if wizard.auto_import_categories:
                        _logger.info(f'Auto-importing categories for connection {self.connection_id.name}')
                        wizard._append_to_connection_log(_('\n📁 Auto-importing categories...'))
                        try:
                            self.connection_id.action_import_categories()
                            wizard._append_to_connection_log(_('✅ Categories imported successfully'))
                            _logger.info('Categories auto-imported successfully')
                        except Exception as cat_error:
                            _logger.error(f'Error auto-importing categories: {cat_error}')
                            wizard._append_to_connection_log(_('⚠️ Error importing categories: %s') % str(cat_error))
                    
                    if wizard.auto_import_coupons:
                        _logger.info(f'Auto-importing coupons for connection {self.connection_id.name}')
                        wizard._append_to_connection_log(_('\n🎫 Auto-importing coupons...'))
                        try:
                            self.connection_id.action_import_coupons()
                            wizard._append_to_connection_log(_('✅ Coupons imported successfully'))
                            _logger.info('Coupons auto-imported successfully')
                        except Exception as coupon_error:
                            _logger.error(f'Error auto-importing coupons: {coupon_error}')
                            wizard._append_to_connection_log(_('⚠️ Error importing coupons: %s') % str(coupon_error))
                except Exception as auto_import_error:
                    _logger.error(f'Error in auto-import process: {auto_import_error}')
                    wizard._append_to_connection_log(_('⚠️ Error in auto-import process: %s') % str(auto_import_error))

                self.connection_id.sudo().write({
                    'import_in_progress_persisted': False,
                })
                self.env.cr.commit()
                

                try:
                    wizard.sudo().write({
                        'state': 'done',
                        'log_message': str(wizard.log_message or '') + _('\n🎉 All batches completed!'),
                    })
                    self.env.cr.commit()
                except Exception as write_error:
                    _logger.warning(f'Could not update wizard state: {write_error}, but import is complete')
                

                cron_name = f'WooCommerce Import - {self.connection_id.name}'
                cron = self.env['ir.cron'].sudo().search([('name', '=', cron_name)], limit=1)
                if cron:
                    cron.sudo().unlink()
                self.env.cr.commit()
                

                if not self.connection_id.import_notification_sent:
                    try:

                        self.env['bus.bus']._sendone(
                            self.env.user.partner_id,
                            'simple_notification',
                            {
                                'title': _('✅ Product Import Completed'),
                                'message': _('Successfully imported %d products from WooCommerce!') % wizard.imported_count,
                                'type': 'success',
                                'sticky': True,
                            }
                        )

                        self.connection_id.sudo().write({'import_notification_sent': True})
                        self.env.cr.commit()
                    except Exception as e:
                        _logger.warning(f'Could not send notification: {e}')
                
                _logger.info(f'Import completed: {wizard.imported_count} products imported')
                
                return
            

            _logger.info(f'Processing batch {wizard.current_batch}/{wizard.total_batches} for connection {self.connection_id.name}')
            wizard._import_single_batch()
            

            wizard.invalidate_recordset(['imported_count', 'batches_completed', 'current_batch'])
            wizard = wizard.sudo().exists()
            if not wizard:
                _logger.warning('Wizard record disappeared during batch processing')
                return
            


            # Update connection progress using the new reliable method
            total_to_import = self.import_limit if self.import_limit > 0 else self.total_products
            wizard._update_connection_progress(wizard.imported_count, total_to_import)
            



            
        except Exception as e:
            _logger.error(f'Error in background import batch: {str(e)}')

            self.env.cr.rollback()
            

            error_str = str(e).lower()
            is_concurrency_error = any(term in error_str for term in [
                'serialize', 'concurrent update', 'could not serialize',
                'current transaction is aborted'
            ])
            
            if is_concurrency_error:
                _logger.warning(f'Concurrency error detected, will retry on next cron run: {e}')

                return
            

            try:
                wizard = self.sudo().exists()
                if wizard:
                    wizard.sudo().write({
                        'error_count': wizard.error_count + 1,
                        'log_message': str(wizard.log_message or '') + _('\n❌ Batch %d failed: %s') % (wizard.current_batch, str(e)),
                    })
                    self.env.cr.commit()
            except Exception as update_error:
                _logger.error(f'Could not update wizard error count: {update_error}')
                self.env.cr.rollback()

                try:
                    self.connection_id.sudo().write({
                        'import_in_progress_persisted': False,
                    })
                    self.env.cr.commit()
                except Exception as conn_error:
                    _logger.error(f'Could not update connection status: {conn_error}')
                    self.env.cr.rollback()

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
                        

                        if existing:
                            if self.overwrite_existing:

                                if existing.odoo_product_id:
                                    existing.odoo_product_id.with_context(skip_wc_sync=True).unlink()
                                existing.with_context(skip_wc_sync=True).unlink()
                                log_messages.append(_('🔄 Overwriting: %s') % product_data.get('name', ''))
                            elif self.update_existing:

                                self._update_existing_product(existing, product_data)
                                imported_count += 1
                                log_messages.append(_('🔄 Updated: %s') % product_data.get('name', ''))
                                continue
                            else:

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

                            existing.with_context(importing_from_woocommerce=True).write(wc_product_vals)
                            wc_product = existing
                        else:

                            wc_product = self.env['woocommerce.product'].with_context(importing_from_woocommerce=True).create(wc_product_vals)
                        

                        if self.import_categories and product_data.get('categories'):
                            self._map_product_categories(wc_product, product_data.get('categories'))
                        
                        if self.import_images and product_data.get('images'):
                            download_images = (self.image_download_mode == 'download')
                            for idx, image_data in enumerate(product_data.get('images', [])):
                                try:
                                    image_data['sequence'] = (idx + 1) * 10
                                    self.env['woocommerce.product.image'].create_from_woocommerce_data(
                                        image_data, wc_product.id, download_image=download_images
                                    )
                                except Exception as e:
                                    _logger.error(f"Error importing image: {e}")
                                    continue
                        

                        if self.import_attributes and product_data.get('type') == 'variable' and self.connection_id.import_variants:
                            try:
                                variations = self.connection_id.get_product_variations(product_data.get('id'))
                                if variations:
                                    variation_count = 0
                                    for variation_data in variations:
                                        try:
                                            self.env['woocommerce.variant.mapping'].create_from_woocommerce_variation(
                                                variation_data, wc_product.id
                                            )
                                            variation_count += 1
                                        except Exception as e:
                                            _logger.warning(f"Error importing variation {variation_data.get('id')}: {e}")
                                            continue
                                    

                                    if self.connection_id.auto_create_variants:
                                        for variant_mapping in wc_product.variant_mapping_ids.filtered(lambda v: not v.odoo_variant_id):
                                            try:
                                                variant_mapping.action_create_odoo_variant()
                                            except Exception as e:
                                                _logger.warning(f"Error auto-creating variant: {e}")
                                    
                                    log_messages.append(_('📦 Imported %d variations for: %s') % (variation_count, product_data.get('name', '')))
                            except Exception as e:
                                _logger.warning(f"Error importing variations for product {product_data.get('name')}: {e}")

                        
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
    
    def _import_all_products_immediately(self):
        """Fetch all products from WooCommerce immediately and process them"""
        self.ensure_one()
        
        wizard = self.sudo().exists()
        if not wizard:
            _logger.error('Wizard record not found')
            return
        
        total_to_import = wizard.import_limit if wizard.import_limit > 0 else wizard.total_products
        max_per_page = 100
        
        _logger.info(f'Fetching all {total_to_import} products immediately...')
        all_products = []
        page = 1
        

        while True:
            try:

                remaining = total_to_import - len(all_products)
                if remaining <= 0:
                    break
                
                per_page = min(max_per_page, remaining)
                
                _logger.info(f'Fetching page {page} (per_page={per_page})...')
                products_data = wizard.connection_id.get_products(
                    page=page,
                    per_page=per_page
                )
                
                if not products_data:
                    _logger.info(f'No more products on page {page}')
                    break
                
                all_products.extend(products_data)
                _logger.info(f'Fetched {len(products_data)} products from page {page}. Total: {len(all_products)}')
                

                if len(products_data) < per_page:
                    break
                

                if total_to_import > 0 and len(all_products) >= total_to_import:
                    all_products = all_products[:total_to_import]
                    break
                
                page += 1
                
            except Exception as e:
                _logger.error(f'Error fetching page {page}: {e}')
                break
        
        _logger.info(f'Fetched {len(all_products)} products total. Processing them now...')
        



        try:
            self._process_all_products_at_once(all_products, wizard)
        except Exception as process_error:
            _logger.error(f'Error processing all products: {process_error}')

            try:
                if not self.env.cr.closed:
                    self.env.cr.rollback()
            except Exception:
                pass


        


        try:

            self.env.cr.execute("SELECT 1")
        except Exception:

            try:
                if not self.env.cr.closed:
                    self.env.cr.rollback()
            except Exception:
                pass
    
    def _process_all_products_at_once(self, products_data, wizard):
        """Process all products in batches to avoid timeout"""
        
        batch_imported = 0
        batch_updated = 0
        batch_skipped = 0
        batch_errors = 0
        batch_duplicates = 0
        
        processed_products = set()
        
        # Process in smaller batches to avoid timeout (10 products per batch)
        batch_size = 10
        total_products = len(products_data)
        
        _logger.info(f'Processing {total_products} products in batches of {batch_size}...')
        
        for batch_start in range(0, total_products, batch_size):
            batch_end = min(batch_start + batch_size, total_products)
            batch_products = products_data[batch_start:batch_end]
            batch_num = (batch_start // batch_size) + 1
            total_batches = (total_products + batch_size - 1) // batch_size
            
            _logger.info(f'Processing batch {batch_num}/{total_batches} (products {batch_start+1}-{batch_end} of {total_products})...')
            wizard._append_to_connection_log(_('\n📦 Processing batch %d/%d (products %d-%d)...') % (batch_num, total_batches, batch_start+1, batch_end))
            
            # Process each product in this batch
            for idx_in_batch, product_data in enumerate(batch_products):
                idx = batch_start + idx_in_batch
            product_id = product_data.get('id', f'unknown_{idx}')
            product_name = product_data.get('name', 'Unknown')
            


            if (idx + 1) % 5 == 0 or idx == len(products_data) - 1:
                try:

                    with self.env.registry.cursor() as progress_cr:
                        progress_env = self.env(cr=progress_cr)
                        progress_wizard = progress_env['woocommerce.import.wizard'].browse(wizard.id)
                        if progress_wizard.exists():

                            progress_wizard.write({
                                'progress_message': f'Processing {idx + 1}/{len(products_data)}: {product_name[:30]}...',
                                'progress_current': idx + 1,
                                'progress_total': len(products_data),
                                'batch_size': len(products_data),
                                'total_batches': 1,
                                'current_batch': 1,
                            })
                            

                            try:
                                progress_connection = progress_env['woocommerce.connection'].browse(self.connection_id.id)
                                if progress_connection.exists():
                                    progress_connection.write({
                                        'import_progress_count_persisted': idx + 1,
                                        'import_total_count_persisted': len(products_data),
                                    })
                            except Exception as conn_error:
                                _logger.warning(f'Could not update connection progress: {conn_error}')
                            
                            progress_cr.commit()
                except Exception as progress_error:

                    _logger.warning(f'Could not update progress: {progress_error}')
                    pass
            

            if product_id in processed_products:
                batch_duplicates += 1
                continue
            
            processed_products.add(product_id)
            


            try:

                savepoint_name = f'product_import_{product_id}_{idx}'
                try:
                    self.env.cr.execute(f'SAVEPOINT {savepoint_name}')
                except Exception:
                    pass
                
                try:

                    existing_wc_product = self.env['woocommerce.product'].search([
                        ('wc_product_id', '=', product_id),
                        ('connection_id', '=', wizard.connection_id.id)
                    ], limit=1)
                    
                    if existing_wc_product:
                        if wizard.overwrite_existing:

                            if existing_wc_product.odoo_product_id:
                                existing_wc_product.odoo_product_id.with_context(skip_wc_sync=True).unlink()
                            existing_wc_product.with_context(skip_wc_sync=True).unlink()
                            self.env.cr.commit()


                            self._create_single_product_from_data(product_data, wizard)
                            batch_imported += 1
                            log_msg = _('\n✅ Imported: %s (WC ID: %s)') % (product_name, product_id)
                            wizard._append_to_connection_log(log_msg.strip())
                        elif wizard.update_existing:


                            batch_skipped += 1
                        else:
                            batch_skipped += 1
                    else:

                        self._create_single_product_from_data(product_data, wizard)
                        batch_imported += 1
                        log_msg = _('\n✅ Imported: %s (WC ID: %s)') % (product_name, product_id)
                        wizard._append_to_connection_log(log_msg.strip())
                    

                    try:
                        self.env.cr.execute(f'RELEASE SAVEPOINT {savepoint_name}')
                    except Exception:
                        pass
                        
                except Exception as e:

                    try:
                        self.env.cr.execute(f'ROLLBACK TO SAVEPOINT {savepoint_name}')
                    except Exception:
                        pass
                    _logger.error(f'Error processing product {product_name} (WC ID: {product_id}): {e}')
                    batch_errors += 1
                    error_msg = _('\n❌ Failed: %s (WC ID: %s) - %s') % (product_name, product_id, str(e))
                    wizard._append_to_connection_log(error_msg.strip())
                    
            except Exception as e:
                _logger.error(f'Error processing product {product_name} (WC ID: {product_id}): {e}')
                batch_errors += 1
            
            # Commit and update progress after each batch
            try:
                with self.env.registry.cursor() as batch_cr:
                    batch_env = self.env(cr=batch_cr)
                    batch_wizard = batch_env['woocommerce.import.wizard'].browse(wizard.id)
                    if batch_wizard.exists():
                        batch_wizard.write({
                            'imported_count': batch_imported + batch_updated,
                            'error_count': batch_errors,
                            'progress_current': batch_end,
                            'progress_total': len(products_data),
                            'progress_message': f'✅ Batch {batch_num}/{total_batches} complete: {batch_end}/{len(products_data)} products processed',
                        })
                        
                        batch_connection = batch_env['woocommerce.connection'].browse(self.connection_id.id)
                        if batch_connection.exists():
                            batch_connection.write({
                                'import_progress_count_persisted': batch_end,
                                'import_total_count_persisted': len(products_data),
                            })
                        batch_cr.commit()
                
                _logger.info(f'Batch {batch_num}/{total_batches} complete: {batch_end}/{len(products_data)} products processed (imported: {batch_imported}, errors: {batch_errors})')
            except Exception as progress_error:
                _logger.warning(f'Could not update batch progress: {progress_error}')
        

        total_imported = batch_imported + batch_updated
        try:
            with self.env.registry.cursor() as final_cr:
                final_env = self.env(cr=final_cr)
                final_wizard = final_env['woocommerce.import.wizard'].browse(wizard.id)
                if final_wizard.exists():

                    current_imported = final_wizard.imported_count
                    current_errors = final_wizard.error_count
                    
                    final_wizard.write({
                        'imported_count': current_imported + total_imported,
                        'error_count': current_errors + batch_errors,
                        'batches_completed': 1,
                        'current_batch': 2,
                        'progress_message': f'✅ Completed: {total_imported} imported, {batch_errors} errors',
                        'progress_current': len(products_data),
                        'progress_total': len(products_data),
                    })
                    

                    try:
                        final_connection = final_env['woocommerce.connection'].browse(self.connection_id.id)
                        if final_connection.exists():
                            final_connection.write({
                                'import_progress_count_persisted': total_imported,
                                'import_total_count_persisted': len(products_data),
                            })
                    except Exception as conn_error:
                        _logger.warning(f'Could not update connection progress in final update: {conn_error}')
                    
                    final_cr.commit()
        except Exception as final_error:
            _logger.error(f'Error updating final wizard state: {final_error}')

        

        try:
            summary = _('\n✅ Import complete: %d new, %d updated, %d skipped, %d duplicates, %d errors') % (
                batch_imported, batch_updated, batch_skipped, batch_duplicates, batch_errors
            )
            wizard._append_to_connection_log(summary)
        except Exception:
            pass
        

        try:
            with self.env.registry.cursor() as cleanup_cr:
                cleanup_env = self.env(cr=cleanup_cr)
                connection = cleanup_env['woocommerce.connection'].browse(self.connection_id.id)
                if connection.exists():
                    total_imported = batch_imported + batch_updated
                    connection.write({
                        'import_in_progress_persisted': False,
                        'import_progress_count_persisted': total_imported,
                        'import_total_count_persisted': len(products_data),
                    })
                    

                    cron_name = f'WooCommerce Import - {connection.name}'
                    cron = cleanup_env['ir.cron'].sudo().search([('name', '=', cron_name)], limit=1)
                    if cron:
                        cron.sudo().unlink()
                    
                    cleanup_cr.commit()
                    _logger.info(f'Import cleanup complete: {total_imported}/{len(products_data)} products imported')
        except Exception as cleanup_error:
            _logger.error(f'Error cleaning up import state: {cleanup_error}')
    
    def _create_single_product_from_data(self, product_data, wizard):
        """Create a single product from WooCommerce data - extracted from _import_single_batch"""

        product_cr = None
        try:
            product_cr = self.env.registry.cursor()
            product_env = self.env(cr=product_cr)
            

            product_vals = {
                'name': product_data.get('name', 'Imported Product'),
                'list_price': float(product_data.get('price', product_data.get('regular_price', 0)) or 0),
                'default_code': product_data.get('sku', ''),
                'description': product_data.get('description', ''),
                'description_sale': product_data.get('short_description', ''),
                'sale_ok': product_data.get('status') == 'publish',
                'purchase_ok': True,
                'wc_product_id': product_data.get('id'),
                'wc_connection_id': wizard.connection_id.id,
                'wc_sync_enabled': False,
                'wc_sync_direction': 'wc_to_odoo',
                'wc_sync_status': 'synced',
                'wc_last_sync': fields.Datetime.now(),
                'wc_auto_sync': False,
                'wc_image_sync_enabled': wizard.import_images,
            }
            
            odoo_product = product_env['product.template'].with_context(
                importing_from_woocommerce=True,
                skip_wc_sync=True
            ).create(product_vals)
            

            wc_product_vals = {
                'wc_product_id': product_data.get('id'),
                'connection_id': wizard.connection_id.id,
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
            
            wc_product = product_env['woocommerce.product'].with_context(
                skip_wc_sync=True
            ).create(wc_product_vals)
            

            if wizard.import_images and product_data.get('images'):
                download_images = (wizard.image_download_mode == 'download')
                for image_data in product_data.get('images', []):
                    try:
                        product_env['woocommerce.product.image'].with_context(
                            importing_from_woocommerce=True
                        ).create_from_woocommerce_data(
                            image_data, wc_product.id, download_image=download_images
                        )
                    except Exception as e:
                        _logger.error(f"Error importing image: {e}")
            

            # Process categories and attributes in the same cursor before committing
            # Get wizard in the same environment to avoid cross-cursor issues
            wizard_in_env = product_env['woocommerce.import.wizard'].browse(wizard.id)
            if wizard_in_env.exists():
                if wizard_in_env.import_categories and product_data.get('categories'):
                    wizard_in_env._map_product_categories(wc_product, product_data.get('categories'))

                if wizard_in_env.import_attributes:
                    wizard_in_env._process_product_attributes(odoo_product, product_data)
            
            # Commit the transaction - all work is done in this cursor
            # If we reach here without exception, the records were created successfully
            product_cr.commit()
            
            # Store IDs for potential later use (but don't verify existence across cursors)
            # The records are created successfully if we reach here without exception
            odoo_product_id = odoo_product.id
            wc_product_id = wc_product.id
            
            # Close the separate cursor
            if product_cr and not product_cr.closed:
                try:
                    product_cr.close()
                except Exception:
                    pass
            product_cr = None
            
        except Exception as e:
            if product_cr:
                try:
                    product_cr.rollback()
                except Exception:
                    pass
                try:
                    if not product_cr.closed:
                        product_cr.close()
                except Exception:
                    pass
            raise
        finally:
            # Ensure cursor is closed
            if product_cr and not product_cr.closed:
                try:
                    product_cr.close()
                except Exception:
                    pass

    def _import_single_batch(self):
        """Import a single batch of products"""
        self.ensure_one()
        

        wizard = self.sudo().exists()
        if not wizard:
            _logger.error('Wizard record not found, cannot process batch')
            return
        

        start_index = (wizard.current_batch - 1) * wizard.batch_size
        total_to_import = wizard.import_limit if wizard.import_limit > 0 else wizard.total_products
        remaining = total_to_import - wizard.imported_count
        
        if remaining <= 0:
            try:
                wizard.write({
                    'state': 'done',
                    'log_message': str(wizard.log_message or '') + _('\n✅ All products imported!'),
                })
            except Exception as e:
                _logger.warning(f'Could not update wizard state: {e}')
            return
        

        current_batch_size = min(wizard.batch_size, remaining)
        



        wc_page = wizard.current_batch
        
        try:
            wizard.write({
                'progress_message': f'Processing batch {wizard.current_batch} of {wizard.total_batches}...',
                'progress_total': current_batch_size,
                'progress_current': 0,
            })
        except Exception as e:
            _logger.warning(f'Could not update progress message: {e}')
        
        try:

            _logger.info(f"Fetching batch {wizard.current_batch}: page={wc_page}, per_page={current_batch_size}")
            
            products_data = wizard.connection_id.get_products(
                page=wc_page,
                per_page=current_batch_size
            )
            
            if not products_data:
                _logger.info(f'No more products returned from WooCommerce (page {wc_page}), marking import as complete')

                self.connection_id.sudo().write({
                    'import_in_progress_persisted': False,
                })
                self.env.cr.commit()
                

                cron_name = f'WooCommerce Import - {self.connection_id.name}'
                cron = self.env['ir.cron'].sudo().search([('name', '=', cron_name)], limit=1)
                if cron:
                    cron.sudo().unlink()
                self.env.cr.commit()
                
                try:
                    wizard.write({
                        'log_message': str(wizard.log_message or '') + _('\n⚠️ No more products found. Import complete.'),
                        'state': 'done',
                    })
                    wizard._append_to_connection_log(_('\n⚠️ No more products found. Import complete: %d products imported.') % wizard.imported_count)
                except Exception as e:
                    _logger.warning(f'Could not update wizard: {e}')
                return
            

            batch_imported = 0
            batch_updated = 0
            batch_skipped = 0
            batch_errors = 0
            batch_duplicates = 0
            

            processed_products = set()
            
            for idx, product_data in enumerate(products_data):

                product_id = product_data.get('id', f'unknown_{idx}')
                product_name = product_data.get('name', 'Unknown')
                


                savepoint_name = f'product_import_{product_id}_{idx}'
                try:
                    self.env.cr.execute(f'SAVEPOINT {savepoint_name}')
                except Exception:

                    pass
                
                try:
                    

                    if product_id in processed_products:
                        batch_duplicates += 1
                        try:
                            log_msg = _('\n⚠️ Duplicate in batch: %s (WC ID: %s)') % (product_name, product_id)
                            wizard.write({
                                'log_message': str(wizard.log_message or '') + log_msg
                            })
                            wizard._append_to_connection_log(log_msg.strip())
                        except Exception:
                            pass

                        try:
                            self.env.cr.execute(f'RELEASE SAVEPOINT {savepoint_name}')
                        except Exception:
                            pass
                        continue
                    
                    processed_products.add(product_id)
                    

                    try:
                        wizard.write({
                            'progress_message': f"Batch {wizard.current_batch}/{wizard.total_batches}: Processing {product_name[:30]}...",
                            'progress_current': idx + 1,
                        })
                    except Exception:
                        pass
                    

                    existing_wc_product = self.env['woocommerce.product'].search([
                        ('wc_product_id', '=', product_id),
                        ('connection_id', '=', wizard.connection_id.id)
                    ], limit=1)
                    

                    if existing_wc_product:
                        if wizard.overwrite_existing:

                            if existing_wc_product.odoo_product_id:
                                existing_wc_product.odoo_product_id.with_context(skip_wc_sync=True).unlink()
                            existing_wc_product.with_context(skip_wc_sync=True).unlink()

                            self.env.cr.commit()
                            batch_imported += 1
                            try:
                                log_msg = _('\n🔄 Overwriting: %s (WC ID: %s)') % (product_name, product_id)
                                wizard.write({
                                    'log_message': str(wizard.log_message or '') + log_msg
                                })
                                wizard._append_to_connection_log(log_msg.strip())
                            except Exception:
                                pass
                        elif wizard.update_existing:

                            update_cr = None
                            try:
                                update_cr = self.env.registry.cursor()
                                update_env = self.env(cr=update_cr)
                                

                                wc_product_update = update_env['woocommerce.product'].browse(existing_wc_product.id)
                                if wc_product_update.exists():

                                    odoo_product_update = wc_product_update.odoo_product_id
                                    if odoo_product_update:

                                        update_vals = {
                                            'name': product_data.get('name', odoo_product_update.name),
                                            'list_price': float(product_data.get('price', product_data.get('regular_price', 0)) or 0),
                                            'default_code': product_data.get('sku', odoo_product_update.default_code),
                                            'description': product_data.get('description', odoo_product_update.description),
                                            'description_sale': product_data.get('short_description', odoo_product_update.description_sale),
                                            'sale_ok': product_data.get('status') == 'publish',
                                            'wc_last_sync': fields.Datetime.now(),
                                            'wc_sync_status': 'synced',
                                        }
                                        

                                        odoo_product_update.with_context(
                                            importing_from_woocommerce=True,
                                            skip_wc_sync=True
                                        ).write(update_vals)
                                        

                                        if wizard.import_categories and product_data.get('categories'):
                                            wizard._map_product_categories(wc_product_update, product_data.get('categories'))
                                        

                                        if wizard.import_attributes:
                                            wizard._process_product_attributes(odoo_product_update, product_data)
                                        

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
                                        
                                        wc_product_update.with_context(skip_wc_sync=True).write(wc_update_vals)
                                        
                                        update_cr.commit()
                                        batch_updated += 1
                                        try:
                                            log_msg = _('\n🔄 Updated: %s (WC ID: %s)') % (product_name, product_id)
                                            wizard._append_to_connection_log(log_msg.strip())
                                            
                                            # Progress will be updated after batch completion
                                            # (updating here would cause too many database calls)
                                        except Exception:
                                            pass
                                    else:
                                        _logger.warning(f'WooCommerce product {wc_product_update.wc_product_id} has no linked Odoo product')
                                        update_cr.rollback()
                                else:
                                    _logger.warning(f'WooCommerce product {existing_wc_product.id} no longer exists, skipping update')
                                    update_cr.rollback()
                                    
                            except Exception as update_error:
                                if update_cr:
                                    try:
                                        update_cr.rollback()
                                    except Exception:
                                        pass
                                error_str = str(update_error).lower()
                                if 'serialize' in error_str or 'concurrent' in error_str:
                                    _logger.warning(f'Concurrency error updating product {product_name} (WC ID: {product_id}): {update_error}')
                                else:
                                    _logger.error(f'Error updating product {product_name} (WC ID: {product_id}): {update_error}')

                                batch_errors += 1
                                try:
                                    error_msg = _('\n❌ Failed: %s (WC ID: %s) - %s') % (product_name, product_id, str(update_error))
                                    wizard._append_to_connection_log(error_msg.strip())
                                except Exception:
                                    pass
                            finally:
                                if update_cr and not update_cr.closed:
                                    try:
                                        update_cr.close()
                                    except Exception:
                                        pass
                            continue
                        else:

                            batch_skipped += 1
                            try:
                                log_msg = _('\n⏭️  Skipping: %s (already exists, WC ID: %s)') % (product_name, product_id)
                                wizard.write({
                                    'log_message': str(wizard.log_message or '') + log_msg
                                })
                                wizard._append_to_connection_log(log_msg.strip())
                            except Exception:
                                pass
                            continue
                    


                    product_cr = None
                    try:
                        product_cr = self.env.registry.cursor()
                        product_env = self.env(cr=product_cr)
                        

                        product_vals = {
                            'name': product_data.get('name', 'Imported Product'),
                            'list_price': float(product_data.get('price', product_data.get('regular_price', 0)) or 0),
                            'default_code': product_data.get('sku', ''),
                            'description': product_data.get('description', ''),
                            'description_sale': product_data.get('short_description', ''),
                            'sale_ok': product_data.get('status') == 'publish',
                            'purchase_ok': True,
                            'wc_product_id': product_data.get('id'),
                            'wc_connection_id': wizard.connection_id.id,
                            'wc_sync_enabled': False,
                            'wc_sync_direction': 'wc_to_odoo',
                            'wc_sync_status': 'synced',
                            'wc_last_sync': fields.Datetime.now(),
                            'wc_auto_sync': False,
                            'wc_image_sync_enabled': wizard.import_images,
                        }
                        
                        odoo_product = product_env['product.template'].with_context(
                            importing_from_woocommerce=True,
                            skip_wc_sync=True
                        ).create(product_vals)
                        





                        

                        wc_product_vals = {
                            'wc_product_id': product_data.get('id'),
                            'connection_id': wizard.connection_id.id,
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
                        
                        wc_product = product_env['woocommerce.product'].with_context(
                            skip_wc_sync=True
                        ).create(wc_product_vals)
                        

                        if wizard.import_images and product_data.get('images'):
                            download_images = (wizard.image_download_mode == 'download')
                            for image_data in product_data.get('images', []):
                                try:
                                    product_env['woocommerce.product.image'].with_context(
                                        importing_from_woocommerce=True
                                    ).create_from_woocommerce_data(
                                        image_data, wc_product.id, download_image=download_images
                                    )
                                except Exception as e:
                                    _logger.error(f"Error importing image: {e}")
                        
                        # Do category and attribute mapping BEFORE committing/closing cursor
                        # This ensures we're working with records in the same transaction
                        if wizard.import_categories and product_data.get('categories'):
                            try:
                                # Refresh wc_product to ensure it's accessible
                                wc_product.invalidate_recordset()
                                wc_product = product_env['woocommerce.product'].browse(wc_product.id)
                                if wc_product.exists():
                                    # Use product_env to access wizard for category mapping
                                    wizard_for_cat = product_env['woocommerce.import.wizard'].browse(wizard.id)
                                    if wizard_for_cat.exists():
                                        wizard_for_cat._map_product_categories(wc_product, product_data.get('categories'))
                            except Exception as cat_error:
                                _logger.warning(f"Error mapping categories for {product_name} (WC ID: {product_id}): {cat_error}")
                        
                        if wizard.import_attributes:
                            try:
                                # Refresh odoo_product to ensure it's accessible
                                odoo_product.invalidate_recordset()
                                odoo_product = product_env['product.template'].browse(odoo_product.id)
                                if odoo_product.exists():
                                    # Use product_env to access wizard for attribute processing
                                    wizard_for_attr = product_env['woocommerce.import.wizard'].browse(wizard.id)
                                    if wizard_for_attr.exists():
                                        wizard_for_attr._process_product_attributes(odoo_product, product_data)
                            except Exception as attr_error:
                                _logger.warning(f"Error processing attributes for {product_name} (WC ID: {product_id}): {attr_error}")

                        product_cr.commit()
                        
                        # Mark as successfully imported - product was created successfully
                        # Don't try to access from main cursor as it may not see the record yet
                        
                    except Exception as e:
                        if product_cr:
                            try:
                                product_cr.rollback()
                            except Exception:
                                pass
                            try:
                                product_cr.close()
                            except Exception:
                                pass
                        raise
                    finally:
                        if product_cr and not product_cr.closed:
                            try:
                                product_cr.close()
                            except Exception:
                                pass
                    
                    batch_imported += 1
                    try:
                        log_msg = _('\n✅ Imported: %s (WC ID: %s)') % (product_name, product_id)
                        wizard.write({
                            'log_message': str(wizard.log_message or '') + log_msg
                        })
                        wizard._append_to_connection_log(log_msg.strip())
                        
                        # Progress will be updated after batch completion
                        # (updating here would cause too many database calls)
                    except Exception:
                        pass
                    
                except Exception as e:
                    batch_errors += 1
                    product_id = product_data.get('id', 'N/A')
                    product_name = product_data.get('name', 'Unknown')
                    error_str = str(e).lower()
                    

                    is_serialization_error = 'serialize' in error_str or 'concurrent' in error_str
                    is_aborted_error = 'aborted' in error_str or 'transaction' in error_str
                    

                    try:
                        self.env.cr.execute(f'ROLLBACK TO SAVEPOINT {savepoint_name}')
                        if is_serialization_error or is_aborted_error:
                            _logger.warning(f"Rolled back to savepoint after serialization error for product {product_name} (WC ID: {product_id})")
                    except Exception as rollback_error:

                        try:
                            if not self.env.cr.closed:
                                self.env.cr.rollback()
                                _logger.warning(f"Full rollback after savepoint rollback failed for product {product_name} (WC ID: {product_id})")
                        except Exception:
                            pass
                    
                    error_msg = _('\n❌ Failed: %s (WC ID: %s) - %s') % (product_name, product_id, str(e))
                    try:

                        wizard._append_to_connection_log(error_msg.strip())
                    except Exception:
                        pass
                    _logger.error(f"Error importing product {product_name} (WC ID: {product_id}): {e}")
                else:

                    try:
                        self.env.cr.execute(f'RELEASE SAVEPOINT {savepoint_name}')
                    except Exception:
                        pass
            



            update_cr = None
            max_update_retries = 3
            update_success = False
            
            for retry_attempt in range(max_update_retries):
                try:
                    update_cr = self.env.registry.cursor()
                    update_env = self.env(cr=update_cr)
                    

                    wizard_update = update_env['woocommerce.import.wizard'].browse(wizard.id)
                    if wizard_update.exists():

                        correct_batch_num = wizard_update.current_batch
                        total_processed = batch_imported + batch_updated
                        

                        batch_summary_parts = []
                        if batch_imported > 0:
                            batch_summary_parts.append(f'{batch_imported} new')
                        if batch_updated > 0:
                            batch_summary_parts.append(f'{batch_updated} updated')
                        if batch_skipped > 0:
                            batch_summary_parts.append(f'{batch_skipped} skipped')
                        if batch_duplicates > 0:
                            batch_summary_parts.append(f'{batch_duplicates} duplicates')
                        if batch_errors > 0:
                            batch_summary_parts.append(f'{batch_errors} errors')
                        
                        summary_text = ', '.join(batch_summary_parts) if batch_summary_parts else '0 processed'
                        
                        batch_log = _('\n\n📦 Batch %d/%d completed: %s\n') % (
                            correct_batch_num, wizard_update.total_batches, summary_text
                        )
                        

                        try:
                            update_cr.execute(
                                "SELECT id FROM woocommerce_import_wizard WHERE id = %s FOR UPDATE NOWAIT",
                                (wizard.id,)
                            )
                        except Exception as lock_error:

                            update_cr.rollback()
                            if retry_attempt < max_update_retries - 1:
                                import time
                                time.sleep(0.1 * (retry_attempt + 1))
                                continue
                            else:
                                _logger.warning(f'Could not lock wizard for update after {max_update_retries} attempts')
                                break
                        

                        new_imported_count = wizard_update.imported_count + batch_imported
                        wizard_update.sudo().write({
                            'imported_count': new_imported_count,
                            'error_count': wizard_update.error_count + batch_errors,
                            'batches_completed': wizard_update.batches_completed + 1,
                            'current_batch': wizard_update.current_batch + 1,
                            'progress_message': f'Batch {correct_batch_num} completed! ({summary_text})',
                            'log_message': str(wizard_update.log_message or '') + batch_log,
                        })
                        

                        wizard_update._append_to_connection_log(batch_log.strip())
                        
                        # Update connection progress after batch completion
                        total_to_import = wizard_update.import_limit if wizard_update.import_limit > 0 else wizard_update.total_products
                        wizard_update._update_connection_progress(new_imported_count, total_to_import)

                        update_cr.commit()
                        update_success = True
                        break
                    else:
                        _logger.warning(f'Wizard {wizard.id} no longer exists, skipping update')
                        update_cr.rollback()
                        break
                    
                except Exception as write_error:
                    if update_cr:
                        try:
                            update_cr.rollback()
                        except Exception:
                            pass
                    error_str = str(write_error).lower()
                    if 'serialize' in error_str or 'concurrent' in error_str:
                        if retry_attempt < max_update_retries - 1:
                            _logger.debug(f'Concurrency error updating wizard (attempt {retry_attempt + 1}/{max_update_retries}), retrying: {write_error}')
                            import time
                            time.sleep(0.2 * (retry_attempt + 1))
                            continue
                        else:
                            _logger.warning(f'Concurrency error updating wizard after {max_update_retries} attempts: {write_error}')
                    else:
                        _logger.warning(f'Could not update wizard after batch: {write_error}, but batch was processed')
                        break
                finally:
                    if update_cr and not update_cr.closed:
                        try:
                            update_cr.close()
                        except Exception:
                            pass
                    update_cr = None
            

            if not update_success:
                try:
                    wizard._append_to_connection_log(f'\n📦 Batch completed: {batch_imported} new, {batch_updated} updated, {batch_errors} errors (wizard update skipped due to concurrency)')
                except Exception:
                    pass
            


            wizard.invalidate_recordset(['batches_completed', 'imported_count', 'current_batch'])
            wizard = wizard.sudo().exists()
            

            total_to_import = wizard.import_limit if wizard.import_limit > 0 else wizard.total_products
            if wizard and (wizard.imported_count >= total_to_import or wizard.batches_completed >= wizard.total_batches):

                try:

                    wizard.connection_id.sudo().write({
                        'import_in_progress_persisted': False,
                    })
                    self.env.cr.commit()
                    

                    cron_name = f'WooCommerce Import - {wizard.connection_id.name}'
                    cron = self.env['ir.cron'].sudo().search([('name', '=', cron_name)], limit=1)
                    if cron:
                        cron.sudo().unlink()
                    self.env.cr.commit()
                    

                    wizard.write({
                        'state': 'done',
                        'progress_message': f'All batches completed! Total: {wizard.imported_count} imported, {wizard.error_count} errors',
                    })
                except Exception as cleanup_error:
                    _logger.warning(f'Error during import completion cleanup: {cleanup_error}')

                    try:
                        wizard.connection_id.sudo().write({
                            'import_in_progress_persisted': False,
                        })
                        self.env.cr.commit()
                    except Exception:
                        pass
            
        except Exception as e:
            _logger.error(f"Error during batch import: {e}")
            error_message = str(e) if e else 'Unknown error occurred'
            
            try:
                wizard = self.sudo().exists()
                if wizard:
                    wizard.write({
                        'state': 'draft',
                        'error_count': wizard.error_count + 1,
                        'log_message': str(wizard.log_message or '') + _('\n❌ Import failed: %s') % error_message,
                    })
            except Exception as update_error:
                _logger.error(f'Could not update wizard error state: {update_error}')
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

                        
                        if len(products_data) < batch_size:
                            break
                        
                        page += 1
                        
                    except Exception as e:
                        _logger.error(f"Error fetching products page {page}: {e}")
                        wizard_record.error_count += 1
                        wizard_record.log_message = str(wizard_record.log_message or '') + _('❌ Error fetching page %d: %s\n') % (page, str(e))
                        break
                

                self.write({
                    'imported_count': wizard_record.imported_count,
                    'error_count': wizard_record.error_count,
                    'log_message': wizard_record.log_message,
                })
                new_cr.commit()
                
            except Exception as e:
                _logger.error(f"Critical error during import: {e}")
                new_cr.rollback()

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

            odoo_product = None
            if existing_wc_product and existing_wc_product.odoo_product_id:
                odoo_product = existing_wc_product.odoo_product_id
            

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
            

            if self.import_categories and wc_data.get('categories'):
                category_id = self._get_or_create_category_with_env(wc_data['categories'], env)
                if category_id:
                    product_vals['categ_id'] = category_id
            

            if self.import_images and wc_data.get('images'):
                image_url = wc_data['images'][0].get('src') if wc_data['images'] else None
                if image_url:
                    try:

                        product_vals['image_1920'] = self._download_image(image_url)
                    except Exception as e:
                        _logger.warning(f"Failed to download image for product {wc_data.get('name')}: {e}")

            

            if odoo_product:

                odoo_product.write(product_vals)
                _logger.info(f"Updated Odoo product: {odoo_product.name}")
            else:

                odoo_product = env['product.template'].create(product_vals)
                _logger.info(f"Created Odoo product: {odoo_product.name}")
            

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

                existing_wc_product.with_context(importing_from_woocommerce=True).write(wc_product_vals)
            else:

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

            wc_category = wc_categories[0]
            category_name = wc_category.get('name', 'Imported Category')
            

            existing_category = env['product.category'].search([
                ('name', '=', category_name)
            ], limit=1)
            
            if existing_category:
                return existing_category.id
            

            new_category = env['product.category'].create({
                'name': category_name,
                'parent_id': False,
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
            
            response = requests.get(image_url, timeout=600)
            response.raise_for_status()
            

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

                wc_category = self.env['woocommerce.category'].search([
                    ('wc_category_id', '=', cat_data['id']),
                    ('connection_id', '=', wc_product.connection_id.id)
                ], limit=1)
                
                if wc_category:
                    category_ids.append(wc_category.id)
                else:

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

            odoo_product = wc_product.odoo_product_id
            
            if not odoo_product:
                _logger.warning(f"WooCommerce product {wc_product.wc_product_id} has no linked Odoo product")
                return
            

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
            

            odoo_product.with_context(
                importing_from_woocommerce=True,
                skip_wc_sync=True
            ).write(update_vals)
            

            self._process_product_attributes(odoo_product, product_data)
            

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
            

            if self.import_images and product_data.get('images'):


                

                download_images = (self.image_download_mode == 'download')
                for image_data in product_data.get('images', []):
                    try:
                        self.env['woocommerce.product.image'].create_from_woocommerce_data(
                            image_data, wc_product.id, download_image=download_images
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

            mappings = self.env['woocommerce.field.mapping'].search([
                ('connection_id', '=', self.connection_id.id),
                ('is_active', '=', True),
                ('mapping_direction', 'in', ['wc_to_odoo', 'bidirectional'])
            ])
            
            if not mappings:
                _logger.info(f"No active field mappings found for connection {self.connection_id.name}")
                return
            

            wc_attributes = wc_product_data.get('attributes', [])
            wc_meta_data = wc_product_data.get('meta_data', [])
            

            attr_lookup = {}
            for attr in wc_attributes:
                if isinstance(attr, dict) and 'name' in attr and 'options' in attr:

                    attr_lookup[attr.get('slug', '')] = attr
                    attr_lookup[attr.get('name', '')] = attr
            

            meta_lookup = {}
            for meta in wc_meta_data:
                if isinstance(meta, dict) and 'key' in meta:
                    meta_lookup[meta['key']] = meta.get('value', '')
            

            update_vals = {}
            for mapping in mappings:
                wc_field = mapping.wc_field_name
                odoo_field = mapping.odoo_field_name
                

                if not hasattr(odoo_product, odoo_field):
                    continue
                
                value = None
                

                if wc_field.startswith('attributes.'):
                    attr_key = wc_field.replace('attributes.', '')
                    if attr_key in attr_lookup:
                        attr_data = attr_lookup[attr_key]
                        if wc_field.endswith('.options'):

                            options = attr_data.get('options', [])
                            value = ', '.join(options) if options else ''
                        else:

                            options = attr_data.get('options', [])
                            value = options[0] if options else ''
                

                elif wc_field.startswith('meta_data.'):
                    meta_key = wc_field.replace('meta_data.', '')
                    value = meta_lookup.get(meta_key, '')
                

                else:
                    value = wc_product_data.get(wc_field, '')
                

                if value and mapping.transform_function != 'none':
                    value = self._apply_field_transformation(value, mapping)
                

                if not value and mapping.default_value:
                    value = mapping.default_value
                

                if value is not None:
                    update_vals[odoo_field] = value
            

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

                value_str = str(value).lower()

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
