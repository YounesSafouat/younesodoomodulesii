import base64
import requests
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class WooCommerceProductImage(models.Model):
    _name = 'woocommerce.product.image'
    _description = 'WooCommerce Product Image'
    _inherit = ['image.mixin']
    _order = 'sequence, id'

    name = fields.Char(
        string='Image Name',
        required=True,
        help='Name of the image'
    )
    
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Order of the image (lower numbers appear first)'
    )
    
    is_main_image = fields.Boolean(
        string='Main Image',
        default=False,
        help='Set as the main product image (will be position 0 in WooCommerce)'
    )
    
    image_1920 = fields.Image(
        string='Image',
        max_width=1920,
        max_height=1920,
        help='Product image (1920x1920)'
    )
    
    image_1024 = fields.Image(
        string='Image 1024',
        related='image_1920',
        max_width=1024,
        max_height=1024,
        store=True
    )
    
    image_512 = fields.Image(
        string='Image 512',
        related='image_1920',
        max_width=512,
        max_height=512,
        store=True
    )
    
    image_256 = fields.Image(
        string='Image 256',
        related='image_1920',
        max_width=256,
        max_height=256,
        store=True
    )
    
    image_128 = fields.Image(
        string='Image 128',
        related='image_1920',
        max_width=128,
        max_height=128,
        store=True
    )
    
    product_id = fields.Many2one(
        'woocommerce.product',
        string='WooCommerce Product',
        required=True,
        ondelete='cascade',
        help='Related WooCommerce product'
    )
    
    wc_image_id = fields.Integer(
        string='WooCommerce Image ID',
        help='Image ID in WooCommerce'
    )
    
    wc_image_url = fields.Char(
        string='WooCommerce Image URL',
        help='URL of the image in WooCommerce'
    )
    
    alt_text = fields.Char(
        string='Alt Text',
        help='Alternative text for the image'
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
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to set default name and trigger sync"""
        _logger.info(f"Creating {len(vals_list)} WooCommerce product image(s)")
        

        for vals in vals_list:
            if not vals.get('name'):
                vals['name'] = f"Image {self.env['woocommerce.product'].browse(vals.get('product_id', 0)).name or 'Unknown'}"
            

            vals['sync_status'] = 'pending'
            vals['sync_error'] = False
            vals['wc_image_id'] = False
            vals['wc_image_url'] = False
        
        _logger.info(f"Creating {len(vals_list)} new image(s) with pending sync status")
        

        records = super(WooCommerceProductImage, self).create(vals_list)
        



        
        return records
    
    def read(self, fields=None, load='_classic_read'):
        """Override read to trigger lazy loading of images if needed"""
        result = super().read(fields=fields, load=load)
        

        if fields is None or 'image_1920' in fields:
            for record in self:
                if not record.image_1920 and record.wc_image_url and record.sync_status == 'pending':
                    try:
                        record._lazy_load_image()

                        updated = record.read(['image_1920'])
                        if updated and updated[0].get('image_1920'):

                            for res in result:
                                if res.get('id') == record.id:
                                    res['image_1920'] = updated[0]['image_1920']
                    except Exception as e:
                        _logger.warning(f"Error lazy loading image during read: {e}")
        
        return result
    
    def write(self, vals):
        """Override write to trigger sync on changes and handle main image logic"""
        if not self.env.context.get('skip_logging'):
            _logger.info(f"Writing to WooCommerce product image {self.name} with vals: {list(vals.keys())}")
        

        if vals.get('is_main_image'):

            self.product_id.product_image_ids.filtered(
                lambda img: img.id != self.id
            ).with_context(skip_logging=True).write({'is_main_image': False})
        

        if 'image_1920' in vals and vals['image_1920']:
            vals['sync_status'] = 'pending'
            vals['sync_error'] = False
            vals['wc_image_id'] = False
            vals['wc_image_url'] = False
            _logger.info(f"Image changed for {self.name}, resetting sync status to pending")
        
        result = super(WooCommerceProductImage, self).write(vals)
        



        

        if vals.get('is_main_image') and not vals.get('sequence'):
            self.write({'sequence': 5})
        
        return result
    
    @api.onchange('image_1920')
    def _onchange_image_1920(self):
        """Handle image change and prepare for sync"""
        if self.image_1920:
            _logger.info(f"Image changed via onchange for {self.name}")

            self.sync_status = 'pending'
            self.sync_error = False
            self.wc_image_id = False
            self.wc_image_url = False
    
    def action_sync_to_woocommerce(self):
        """Sync image to WooCommerce store"""
        self.ensure_one()
        
        if not self.image_1920:
            raise UserError(_('No image to sync'))
        
        try:
            connection = self.product_id.connection_id
            

            if connection.image_upload_method == 'wordpress_media':
                _logger.info(f"Using WordPress Media Library upload method for image {self.name}")
                wc_image_data = self._upload_image_to_woocommerce()
            else:
                _logger.info(f"Using WooCommerce API Base64 upload method for image {self.name}")
                wc_image_data = self._upload_image_to_woocommerce_base64()
            

            self.write({
                'wc_image_id': wc_image_data.get('id'),
                'wc_image_url': wc_image_data.get('src'),
                'sync_status': 'synced',
                'sync_error': False,
            })
            _logger.info(f"Image {self.name} uploaded to WordPress Media Library with ID: {wc_image_data.get('id')}")
            

            self.product_id._sync_to_woocommerce_store()
            

            self.env.cr.commit()
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Image synced to WooCommerce successfully!'),
                    'type': 'success',
                }
            }
            
        except Exception as e:
            _logger.error(f"Error syncing image {self.name} to WooCommerce: {e}")
            self.write({
                'sync_status': 'error',
                'sync_error': str(e),
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Failed to sync image to WooCommerce: %s') % str(e),
                    'type': 'danger',
                }
            }
    
    def _upload_image_via_woocommerce_api(self):
        """Alternative method: Upload image using public URL"""
        self.ensure_one()
        
        if not self.product_id.connection_id:
            raise UserError(_('No WooCommerce connection configured'))
        
        connection = self.product_id.connection_id
        

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        

        if 'localhost' in base_url or '127.0.0.1' in base_url:


            _logger.warning("Odoo is on localhost - WooCommerce cannot access images. Falling back to WordPress Media Library.")
            raise UserError(_('Odoo is running on localhost. WooCommerce cannot access localhost URLs. Please use WordPress Media Library method or set up a public URL for Odoo.'))
        

        image_url = f"{base_url}/web/image/woocommerce.product.image/{self.id}/image_1920.jpg"
        

        image_data = {
            'name': self.name or 'product_image.jpg',
            'src': image_url,
            'alt': self.alt_text or '',
            'position': self.sequence // 10,
        }
        
        _logger.info(f"Uploading image {self.name} via URL: {image_url}")
        
        return image_data
    
    def action_set_as_main_image(self):
        """Set this image as the main product image"""
        self.ensure_one()
        

        other_images = self.product_id.product_image_ids.filtered(lambda img: img.id != self.id)
        if other_images:
            other_images.with_context(skip_logging=True).write({'is_main_image': False})
        

        self.write({
            'is_main_image': True,
            'sequence': 5,
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Image set as main product image!'),
                'type': 'success',
            }
        }
    
    def action_move_up(self):
        """Move image up in sequence"""
        self.ensure_one()
        

        prev_image = self.product_id.product_image_ids.filtered(
            lambda img: img.sequence < self.sequence and not img.is_main_image
        ).sorted('sequence', reverse=True)[:1]
        
        if prev_image:

            old_sequence = self.sequence
            self.write({'sequence': prev_image.sequence})
            prev_image.write({'sequence': old_sequence})
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Image moved up in sequence!'),
                    'type': 'success',
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Info'),
                    'message': _('Image is already at the top!'),
                    'type': 'info',
                }
            }
    
    def action_move_down(self):
        """Move image down in sequence"""
        self.ensure_one()
        

        next_image = self.product_id.product_image_ids.filtered(
            lambda img: img.sequence > self.sequence and not img.is_main_image
        ).sorted('sequence')[:1]
        
        if next_image:

            old_sequence = self.sequence
            self.write({'sequence': next_image.sequence})
            next_image.write({'sequence': old_sequence})
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Image moved down in sequence!'),
                    'type': 'success',
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Info'),
                    'message': _('Image is already at the bottom!'),
                    'type': 'info',
                }
            }
    
    def action_bulk_sync_to_woocommerce(self):
        """Bulk sync multiple images to WooCommerce"""
        images = self.filtered(lambda img: img.image_1920 and img.sync_status != 'synced')
        
        if not images:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Info'),
                    'message': _('No images need syncing.'),
                    'type': 'info',
                }
            }
        
        success_count = 0
        error_count = 0
        error_messages = []
        
        for image in images:
            try:
                image.action_sync_to_woocommerce()
                success_count += 1
            except Exception as e:
                error_count += 1
                error_messages.append(f"{image.name}: {str(e)}")
        
        if error_count == 0:
            message = _('Successfully synced %d images to WooCommerce!') % success_count
            message_type = 'success'
        else:
            message = _('Synced %d images successfully, %d failed.') % (success_count, error_count)
            message_type = 'warning'
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Bulk Sync Complete'),
                'message': message,
                'type': message_type,
                'sticky': error_count > 0,
                'details': '\n'.join(error_messages) if error_messages else None,
            }
        }
    
    def _upload_image_to_woocommerce(self):
        """Upload image to WordPress media library and return WooCommerce format"""
        self.ensure_one()
        
        if not self.product_id.connection_id:
            raise UserError(_('No WooCommerce connection configured'))
        
        connection = self.product_id.connection_id
        
        if not connection.wp_username or not connection.wp_application_password:
            raise UserError(_('WordPress username and application password are required for media upload. Please configure them in the WooCommerce connection settings.'))
        

        clean_password = connection.wp_application_password.replace(' ', '')
        if len(clean_password) != 24:
            raise UserError(_('WordPress Application Password format is invalid. It should be 24 characters (format: xxxx xxxx xxxx xxxx xxxx xxxx). Current length: %d') % len(clean_password))
        
        image_data = base64.b64decode(self.image_1920)
        
        store_url = connection.store_url.rstrip('/')
        wp_api_url = f"{store_url}/wp-json/wp/v2/media"
        
        headers = connection._get_wp_auth_headers()
        headers.update({
            'Content-Type': 'image/jpeg',
            'Content-Disposition': f'attachment; filename="{self.name or "image"}.jpg"'
        })
        
        _logger.info(f"Uploading image {self.name} to WordPress media library")
        _logger.info(f"WordPress API URL: {wp_api_url}")
        _logger.info(f"WordPress Username: {connection.wp_username}")
        _logger.info(f"Application Password configured: {'Yes' if connection.wp_application_password else 'No'}")
        
        try:
            response = requests.post(wp_api_url, headers=headers, data=image_data, timeout=600)
            
            if response.status_code == 401:
                _logger.error(f"WordPress authentication failed (401). Check:")
                _logger.error(f"1. WordPress username: {connection.wp_username}")
                _logger.error(f"2. Application password format (should be: xxxx xxxx xxxx xxxx xxxx xxxx)")
                _logger.error(f"3. User has proper permissions in WordPress")
                _logger.error(f"4. Application password is not expired")
                raise UserError(_("WordPress authentication failed. Please check:\n1. WordPress username is correct\n2. Application password format (xxxx xxxx xxxx xxxx xxxx xxxx)\n3. User has proper permissions\n4. Application password is not expired"))
            
            response.raise_for_status()
            
            wp_response = response.json()
            
            image_info = {
                'id': wp_response.get('id'),
                'src': wp_response.get('source_url'),
                'name': wp_response.get('title', {}).get('rendered', self.name or 'Image'),
                'alt': wp_response.get('alt_text', self.alt_text or ''),
            }
            
            _logger.info(f"Successfully uploaded image to WordPress: {image_info}")
            
            return image_info
            
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error uploading image {self.name} to WordPress: {e}")
            if hasattr(e, 'response') and e.response is not None:
                _logger.error(f"Response status: {e.response.status_code}")
                _logger.error(f"Response text: {e.response.text}")
            raise UserError(_("Failed to upload image to WordPress media library: %s") % str(e))
    
    def _upload_image_to_woocommerce_base64(self):
        """Upload image to WooCommerce using base64 data"""
        self.ensure_one()
        
        if not self.product_id.connection_id:
            raise UserError(_('No WooCommerce connection configured'))
        
        connection = self.product_id.connection_id
        

        image_data = self._process_image_for_woocommerce()
        

        image_data_dict = {
            'name': self.name or 'product_image.jpg',
            'src': image_data,
            'alt': self.alt_text or '',
            'position': self.sequence // 10,
        }
        
        _logger.info(f"Uploading image {self.name} via WooCommerce API Base64")
        
        return image_data_dict
    
    def _process_image_for_woocommerce(self):
        """Process image for WooCommerce API"""
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
            
            _logger.info(f"Original image size: {image.size} for {self.name}")
            
            if image.size[0] > 800 or image.size[1] > 800:
                image.thumbnail((800, 800), Image.Resampling.LANCZOS)
                _logger.info(f"Resized image to: {image.size} for {self.name}")
            
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=85)
            processed_data = base64.b64encode(buffer.getvalue()).decode()
            
            _logger.info(f"Successfully processed image for {self.name}, size: {len(processed_data)} chars")
            return f"data:image/jpeg;base64,{processed_data}"
            
        except Exception as e:
            _logger.error(f"Failed to process image for {self.name}: {str(e)}")
            return None
    
    def action_download_from_woocommerce(self):
        """Download image from WooCommerce"""
        self.ensure_one()
        
        if not self.wc_image_url:
            raise UserError(_('No WooCommerce image URL available'))
        
        try:
            response = requests.get(self.wc_image_url, timeout=600)
            response.raise_for_status()
            
            image_data = base64.b64encode(response.content).decode('utf-8')
            
            self.write({
                'image_1920': image_data,
                'sync_status': 'synced',
                'sync_error': False,
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Image downloaded from WooCommerce successfully!'),
                    'type': 'success',
                }
            }
            
        except Exception as e:
            _logger.error(f"Error downloading image {self.name} from WooCommerce: {e}")
            self.write({
                'sync_status': 'error',
                'sync_error': str(e),
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Failed to download image from WooCommerce: %s') % str(e),
                    'type': 'danger',
                }
            }
    
    def _lazy_load_image(self):
        """Lazy load image from URL if not already downloaded"""
        if self.image_1920:
            return
        
        if not self.wc_image_url:
            _logger.warning(f"No image URL available for {self.name}")
            return
        
        try:
            _logger.info(f"Lazy loading image: {self.name} from {self.wc_image_url}")
            response = requests.get(
                self.wc_image_url,
                timeout=600,
                stream=True,
                headers={'User-Agent': 'Odoo-WooCommerce-Integration/1.0'}
            )
            response.raise_for_status()
            
            content_length = response.headers.get('content-length')
            if content_length and int(content_length) > 10 * 1024 * 1024:
                _logger.warning(f"Image too large ({int(content_length) / 1024 / 1024:.2f} MB): {self.wc_image_url}")
                self.sync_status = 'error'
                self.sync_error = f"Image too large: {int(content_length) / 1024 / 1024:.2f} MB"
                return
            
            image_data = base64.b64encode(response.content).decode('utf-8')
            self.image_1920 = image_data
            self.sync_status = 'synced'
            self.sync_error = False
            _logger.info(f"Successfully lazy loaded image: {self.name}")
            
        except Exception as e:
            _logger.warning(f"Error lazy loading image {self.name}: {e}")
            self.sync_status = 'error'
            self.sync_error = str(e)
    
    @api.model
    def create_from_woocommerce_data(self, wc_image_data, product_id, download_image=True):
        """Create image record from WooCommerce data
        
        Args:
            wc_image_data: Dictionary containing WooCommerce image data
            product_id: ID of the WooCommerce product
            download_image: If True, download the image immediately. If False, store only the URL for lazy loading.
        """
        try:
            product = self.env['woocommerce.product'].browse(product_id)
            sequence = wc_image_data.get('sequence', 10)
            
            image_name = wc_image_data.get('alt') or wc_image_data.get('name')
            if not image_name:
                image_name = f"{product.name} - Image {sequence // 10}"
            
            vals = {
                'name': image_name,
                'sequence': sequence,
                'product_id': product_id,
                'wc_image_id': wc_image_data.get('id'),
                'wc_image_url': wc_image_data.get('src'),
                'alt_text': wc_image_data.get('alt'),
                'sync_status': 'pending' if not download_image else 'synced',
            }
            
            image_url = wc_image_data.get('src')
            if image_url and download_image:
                max_retries = 3
                retry_count = 0
                download_success = False
                
                while retry_count < max_retries and not download_success:
                    try:
                        _logger.info(f"Downloading image (attempt {retry_count + 1}/{max_retries}): {image_name}")
                        
                        response = requests.get(
                            image_url, 
                            timeout=600,
                            stream=True,
                            headers={'User-Agent': 'Odoo-WooCommerce-Integration/1.0'}
                        )
                        response.raise_for_status()
                        
                        content_length = response.headers.get('content-length')
                        if content_length and int(content_length) > 10 * 1024 * 1024:
                            _logger.warning(f"Image too large ({int(content_length) / 1024 / 1024:.2f} MB): {image_url}")
                            vals['sync_status'] = 'error'
                            vals['sync_error'] = f"Image too large: {int(content_length) / 1024 / 1024:.2f} MB"
                            break
                        
                        image_data = base64.b64encode(response.content).decode('utf-8')
                        vals['image_1920'] = image_data
                        vals['sync_status'] = 'synced'
                        vals['wc_image_id'] = wc_image_data.get('id')
                        vals['wc_image_url'] = image_url
                        download_success = True
                        
                        _logger.info(f"Successfully downloaded image: {image_name}")
                        
                    except requests.exceptions.Timeout:
                        retry_count += 1
                        if retry_count >= max_retries:
                            _logger.warning(f"Image download timed out after {max_retries} attempts: {image_url}")
                            vals['sync_status'] = 'error'
                            vals['sync_error'] = f"Download timeout after {max_retries} attempts"
                        else:
                            _logger.info(f"Timeout, retrying ({retry_count}/{max_retries})...")
                            
                    except requests.exceptions.RequestException as e:
                        retry_count += 1
                        if retry_count >= max_retries:
                            _logger.warning(f"Failed to download image from {image_url}: {e}")
                            vals['sync_status'] = 'error'
                            vals['sync_error'] = f"Download failed: {str(e)}"
                        else:
                            _logger.info(f"Request failed, retrying ({retry_count}/{max_retries})...")
                            
                    except Exception as e:
                        _logger.warning(f"Unexpected error downloading image from {image_url}: {e}")
                        vals['sync_status'] = 'error'
                        vals['sync_error'] = f"Download failed: {str(e)}"
                        break
            
            return self.create(vals)
            
        except Exception as e:
            _logger.error(f"Error creating image from WooCommerce data: {e}")
            raise
