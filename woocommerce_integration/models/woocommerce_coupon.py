import json
import requests
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


class WooCommerceCoupon(models.Model):
    _name = 'woocommerce.coupon'
    _description = 'WooCommerce Coupon'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'code'
    _rec_name = 'code'

    name = fields.Char(
        string='Coupon Name',
        required=True,
        help='Internal name for this coupon'
    )
    
    code = fields.Char(
        string='Coupon Code',
        required=True,
        help='The coupon code that customers will use (must be unique)'
    )
    
    connection_id = fields.Many2one(
        'woocommerce.connection',
        string='WooCommerce Connection',
        required=True,
        ondelete='cascade',
        help='WooCommerce connection'
    )
    
    wc_coupon_id = fields.Integer(
        string='WooCommerce Coupon ID',
        readonly=True,
        help='Coupon ID in WooCommerce'
    )
    
    discount_type = fields.Selection([
        ('fixed_cart', 'Fixed Cart Discount'),
        ('fixed_product', 'Fixed Product Discount'),
        ('percent', 'Percentage Discount'),
        ('percent_product', 'Percentage Product Discount'),
    ], string='Discount Type', required=True, default='percent',
       help='Type of discount to apply')
    
    amount = fields.Float(
        string='Discount Amount',
        required=True,
        default=0.0,
        help='Discount amount. For percentage discounts, enter the percentage (e.g., 10 for 10%)'
    )
    
    description = fields.Text(
        string='Description',
        help='Coupon description (visible to customers)'
    )
    
    date_expires = fields.Datetime(
        string='Expiry Date',
        help='Coupon expiration date (leave empty for no expiration)'
    )
    
    date_expires_gmt = fields.Datetime(
        string='Expiry Date (GMT)',
        readonly=True,
        help='Coupon expiration date in GMT'
    )
    
    usage_limit = fields.Integer(
        string='Usage Limit',
        help='Maximum number of times this coupon can be used (0 = unlimited)'
    )
    
    usage_limit_per_user = fields.Integer(
        string='Usage Limit Per User',
        help='Maximum number of times this coupon can be used per customer (0 = unlimited)'
    )
    
    limit_usage_to_x_items = fields.Integer(
        string='Limit Usage to X Items',
        help='Limit coupon to X number of items in the cart (0 = unlimited)'
    )
    
    free_shipping = fields.Boolean(
        string='Free Shipping',
        default=False,
        help='Allow free shipping when this coupon is applied'
    )
    
    exclude_sale_items = fields.Boolean(
        string='Exclude Sale Items',
        default=False,
        help='Exclude items that are on sale from this coupon'
    )
    
    minimum_amount = fields.Float(
        string='Minimum Amount',
        help='Minimum order amount required to use this coupon'
    )
    
    maximum_amount = fields.Float(
        string='Maximum Amount',
        help='Maximum order amount this coupon can be applied to'
    )
    
    individual_use = fields.Boolean(
        string='Individual Use Only',
        default=False,
        help='This coupon cannot be used in conjunction with other coupons'
    )
    
    usage_count = fields.Integer(
        string='Usage Count',
        readonly=True,
        help='Number of times this coupon has been used'
    )
    
    email_restrictions = fields.Text(
        string='Email Restrictions',
        help='Comma-separated list of email addresses that can use this coupon (one per line)'
    )
    
    product_ids = fields.Many2many(
        'product.template',
        'woocommerce_coupon_product_rel',
        'coupon_id',
        'product_id',
        string='Products',
        help='Products that this coupon can be applied to (leave empty for all products)'
    )
    
    excluded_product_ids = fields.Many2many(
        'product.template',
        'woocommerce_coupon_excluded_product_rel',
        'coupon_id',
        'product_id',
        string='Excluded Products',
        help='Products that this coupon cannot be applied to'
    )
    
    product_category_ids = fields.Many2many(
        'product.category',
        'woocommerce_coupon_category_rel',
        'coupon_id',
        'category_id',
        string='Product Categories',
        help='Product categories that this coupon can be applied to'
    )
    
    excluded_product_category_ids = fields.Many2many(
        'product.category',
        'woocommerce_coupon_excluded_category_rel',
        'coupon_id',
        'category_id',
        string='Excluded Categories',
        help='Product categories that this coupon cannot be applied to'
    )
    
    status = fields.Selection([
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('disabled', 'Disabled'),
    ], string='Status', compute='_compute_status', store=False)
    
    is_expired = fields.Boolean(
        string='Is Expired',
        compute='_compute_is_expired',
        store=True,
        help='Indicates if the coupon has expired.'
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
    
    last_sync = fields.Datetime(
        string='Last Sync',
        readonly=True,
        help='Last time this coupon was synchronized'
    )
    
    wc_data = fields.Text(
        string='WooCommerce Data',
        help='Raw JSON data from WooCommerce'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Uncheck to archive this coupon'
    )
    
    @api.depends('date_expires', 'usage_limit', 'usage_count')
    def _compute_status(self):
        """Compute coupon status"""
        for coupon in self:
            if coupon.date_expires and fields.Datetime.now() > coupon.date_expires:
                coupon.status = 'expired'
            elif coupon.usage_limit and coupon.usage_count >= coupon.usage_limit:
                coupon.status = 'disabled'
            else:
                coupon.status = 'active'
    
    @api.depends('date_expires')
    def _compute_is_expired(self):
        """Compute if coupon is expired"""
        for coupon in self:
            if coupon.date_expires and fields.Datetime.now() > coupon.date_expires:
                coupon.is_expired = True
            else:
                coupon.is_expired = False
    
    @api.constrains('code', 'connection_id')
    def _check_code_unique(self):
        """Ensure coupon code is unique per connection"""
        for coupon in self:
            existing = self.search([
                ('code', '=', coupon.code),
                ('connection_id', '=', coupon.connection_id.id),
                ('id', '!=', coupon.id)
            ])
            if existing:
                raise ValidationError(_('Coupon code "%s" already exists for this connection.') % coupon.code)
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to sync to WooCommerce"""
        coupons = super(WooCommerceCoupon, self).create(vals_list)
        
        for coupon in coupons:
            if coupon.connection_id and coupon.code:
                try:
                    coupon.action_sync_to_woocommerce()
                except Exception as e:
                    _logger.error(f"Error syncing coupon to WooCommerce on create: {e}")
                    coupon.write({
                        'sync_status': 'error',
                        'sync_error': str(e)
                    })
        
        return coupons
    
    def write(self, vals):
        """Override write to sync changes to WooCommerce"""
        # Protect sensitive fields from being changed
        sensitive_fields = ['wc_coupon_id', 'connection_id']
        for field in sensitive_fields:
            if field in vals:
                for coupon in self:
                    if coupon[field] and vals[field] != coupon[field]:
                        raise UserError(_('Cannot change %s. This is a sensitive field that links the coupon to WooCommerce. Changing it could break synchronization.') % field)
        
        result = super(WooCommerceCoupon, self).write(vals)
        
        sync_fields = [
            'code', 'discount_type', 'amount', 'description', 'date_expires',
            'usage_limit', 'usage_limit_per_user', 'limit_usage_to_x_items',
            'free_shipping', 'exclude_sale_items', 'minimum_amount', 'maximum_amount',
            'individual_use', 'email_restrictions', 'product_ids', 'excluded_product_ids',
            'product_category_ids', 'excluded_product_category_ids', 'active'
        ]
        
        if any(key in vals for key in sync_fields):
            for coupon in self:
                if coupon.connection_id and coupon.wc_coupon_id:
                    try:
                        coupon.action_sync_to_woocommerce()
                    except Exception as e:
                        _logger.error(f"Error syncing coupon {coupon.code} to WooCommerce: {e}")
                        coupon.write({
                            'sync_status': 'error',
                            'sync_error': str(e)
                        })
        
        return result
    
    def _prepare_woocommerce_data(self):
        """Prepare coupon data for WooCommerce API"""
        self.ensure_one()
        
        data = {
            'code': self.code,
            'discount_type': self.discount_type,
            'amount': str(self.amount),
            'description': self.description or '',
            'individual_use': self.individual_use,
            'free_shipping': self.free_shipping,
            'exclude_sale_items': self.exclude_sale_items,
        }
        
        if self.date_expires:
            data['date_expires'] = self.date_expires.strftime('%Y-%m-%dT%H:%M:%S')
        else:
            data['date_expires'] = ''
        
        if self.usage_limit:
            data['usage_limit'] = self.usage_limit
        else:
            data['usage_limit'] = 0
        
        if self.usage_limit_per_user:
            data['usage_limit_per_user'] = self.usage_limit_per_user
        else:
            data['usage_limit_per_user'] = 0
        
        if self.limit_usage_to_x_items:
            data['limit_usage_to_x_items'] = self.limit_usage_to_x_items
        else:
            data['limit_usage_to_x_items'] = 0
        
        if self.minimum_amount:
            data['minimum_amount'] = str(self.minimum_amount)
        else:
            data['minimum_amount'] = ''
        
        if self.maximum_amount:
            data['maximum_amount'] = str(self.maximum_amount)
        else:
            data['maximum_amount'] = ''
        
        if self.email_restrictions:
            emails = [email.strip() for email in self.email_restrictions.split('\n') if email.strip()]
            data['email_restrictions'] = emails
        else:
            data['email_restrictions'] = []
        
        if self.product_ids:
            wc_product_ids = []
            for product in self.product_ids:
                if product.wc_product_id and product.wc_connection_id == self.connection_id:
                    wc_product_ids.append(product.wc_product_id)
            data['product_ids'] = wc_product_ids
        else:
            data['product_ids'] = []
        
        if self.excluded_product_ids:
            wc_product_ids = []
            for product in self.excluded_product_ids:
                if product.wc_product_id and product.wc_connection_id == self.connection_id:
                    wc_product_ids.append(product.wc_product_id)
            data['excluded_product_ids'] = wc_product_ids
        else:
            data['excluded_product_ids'] = []
        
        if self.product_category_ids:
            wc_category_ids = []
            for category in self.product_category_ids:
                wc_category = self.env['woocommerce.category'].search([
                    ('odoo_category_id', '=', category.id),
                    ('connection_id', '=', self.connection_id.id)
                ], limit=1)
                if wc_category:
                    wc_category_ids.append(wc_category.wc_category_id)
            data['product_categories'] = wc_category_ids
        else:
            data['product_categories'] = []
        
        if self.excluded_product_category_ids:
            wc_category_ids = []
            for category in self.excluded_product_category_ids:
                wc_category = self.env['woocommerce.category'].search([
                    ('odoo_category_id', '=', category.id),
                    ('connection_id', '=', self.connection_id.id)
                ], limit=1)
                if wc_category:
                    wc_category_ids.append(wc_category.wc_category_id)
            data['excluded_product_categories'] = wc_category_ids
        else:
            data['excluded_product_categories'] = []
        
        return data
    
    def action_sync_to_woocommerce(self):
        """Sync coupon to WooCommerce store"""
        self.ensure_one()
        
        if not self.connection_id:
            raise UserError(_('No WooCommerce connection configured'))
        
        try:
            coupon_data = self._prepare_woocommerce_data()
            
            if self.wc_coupon_id:
                response = self.connection_id.update_coupon(self.wc_coupon_id, coupon_data)
                _logger.info(f"Updated WooCommerce coupon {self.wc_coupon_id}: {self.code}")
            else:
                response = self.connection_id.create_coupon(coupon_data)
                if response and response.get('id'):
                    self.write({
                        'wc_coupon_id': response['id'],
                        'sync_status': 'synced',
                        'last_sync': fields.Datetime.now(),
                        'sync_error': False,
                        'wc_data': json.dumps(response),
                    })
                    _logger.info(f"Created WooCommerce coupon {response['id']}: {self.code}")
                else:
                    raise UserError(_('Failed to create coupon in WooCommerce: No ID returned'))
            
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
                    'message': _('Coupon synced to WooCommerce successfully!'),
                    'type': 'success',
                }
            }
            
        except Exception as e:
            _logger.error(f"Error syncing coupon {self.code} to WooCommerce: {e}")
            self.write({
                'sync_status': 'error',
                'sync_error': str(e),
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Failed to sync coupon to WooCommerce: %s') % str(e),
                    'type': 'danger',
                }
            }
    
    def action_sync_from_woocommerce(self):
        """Sync coupon data from WooCommerce"""
        self.ensure_one()
        
        if not self.wc_coupon_id or not self.connection_id:
            raise UserError(_('This coupon is not linked to a WooCommerce coupon'))
        
        try:
            wc_data = self.connection_id.get_coupon(self.wc_coupon_id)
            
            self._update_from_woocommerce_data(wc_data)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Successful'),
                    'message': _('Coupon synchronized successfully from WooCommerce.'),
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            _logger.error(f"Error syncing coupon {self.id} from WooCommerce: {e}")
            self.write({
                'sync_status': 'error',
                'sync_error': str(e),
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Failed'),
                    'message': _('Failed to sync coupon from WooCommerce: %s') % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
    
    def _update_from_woocommerce_data(self, wc_data):
        """Update coupon fields from WooCommerce data"""
        self.ensure_one()
        
        vals = {
            'code': wc_data.get('code', ''),
            'discount_type': wc_data.get('discount_type', 'percent'),
            'amount': float(wc_data.get('amount', 0)),
            'description': wc_data.get('description', ''),
            'individual_use': wc_data.get('individual_use', False),
            'free_shipping': wc_data.get('free_shipping', False),
            'exclude_sale_items': wc_data.get('exclude_sale_items', False),
            'usage_limit': wc_data.get('usage_limit', 0),
            'usage_limit_per_user': wc_data.get('usage_limit_per_user', 0),
            'limit_usage_to_x_items': wc_data.get('limit_usage_to_x_items', 0),
            'usage_count': wc_data.get('usage_count', 0),
            'wc_data': json.dumps(wc_data),
            'last_sync': fields.Datetime.now(),
            'sync_status': 'synced',
            'sync_error': False,
        }
        
        if wc_data.get('date_expires'):
            try:
                date_expires = datetime.fromisoformat(wc_data['date_expires'].replace('Z', '+00:00'))
                vals['date_expires'] = date_expires
                vals['date_expires_gmt'] = date_expires
            except:
                pass
        
        if wc_data.get('minimum_amount'):
            vals['minimum_amount'] = float(wc_data['minimum_amount'])
        else:
            vals['minimum_amount'] = 0.0
        
        if wc_data.get('maximum_amount'):
            vals['maximum_amount'] = float(wc_data['maximum_amount'])
        else:
            vals['maximum_amount'] = 0.0
        
        if wc_data.get('email_restrictions'):
            vals['email_restrictions'] = '\n'.join(wc_data['email_restrictions'])
        else:
            vals['email_restrictions'] = ''
        
        if wc_data.get('product_ids'):
            product_ids = []
            for wc_product_id in wc_data['product_ids']:
                product = self.env['product.template'].search([
                    ('wc_product_id', '=', wc_product_id),
                    ('wc_connection_id', '=', self.connection_id.id)
                ], limit=1)
                if product:
                    product_ids.append(product.id)
            vals['product_ids'] = [(6, 0, product_ids)]
        
        if wc_data.get('excluded_product_ids'):
            product_ids = []
            for wc_product_id in wc_data['excluded_product_ids']:
                product = self.env['product.template'].search([
                    ('wc_product_id', '=', wc_product_id),
                    ('wc_connection_id', '=', self.connection_id.id)
                ], limit=1)
                if product:
                    product_ids.append(product.id)
            vals['excluded_product_ids'] = [(6, 0, product_ids)]
        
        if wc_data.get('product_categories'):
            category_ids = []
            for wc_category_id in wc_data['product_categories']:
                wc_category = self.env['woocommerce.category'].search([
                    ('wc_category_id', '=', wc_category_id),
                    ('connection_id', '=', self.connection_id.id)
                ], limit=1)
                if wc_category and wc_category.odoo_category_id:
                    category_ids.append(wc_category.odoo_category_id.id)
            vals['product_category_ids'] = [(6, 0, category_ids)]
        
        if wc_data.get('excluded_product_categories'):
            category_ids = []
            for wc_category_id in wc_data['excluded_product_categories']:
                wc_category = self.env['woocommerce.category'].search([
                    ('wc_category_id', '=', wc_category_id),
                    ('connection_id', '=', self.connection_id.id)
                ], limit=1)
                if wc_category and wc_category.odoo_category_id:
                    category_ids.append(wc_category.odoo_category_id.id)
            vals['excluded_product_category_ids'] = [(6, 0, category_ids)]
        
        self.write(vals)
    
    def action_delete_from_woocommerce(self):
        """Delete coupon from WooCommerce"""
        self.ensure_one()
        
        if not self.wc_coupon_id or not self.connection_id:
            raise UserError(_('This coupon is not linked to a WooCommerce coupon'))
        
        try:
            self.connection_id.delete_coupon(self.wc_coupon_id)
            self.write({
                'wc_coupon_id': False,
                'sync_status': 'pending',
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Coupon deleted from WooCommerce successfully!'),
                    'type': 'success',
                }
            }
            
        except Exception as e:
            _logger.error(f"Error deleting coupon {self.code} from WooCommerce: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Failed to delete coupon from WooCommerce: %s') % str(e),
                    'type': 'danger',
                }
            }
    
    @api.model
    def create_from_wc_data(self, wc_data, connection_id):
        """Create WooCommerce coupon from WooCommerce API data"""
        connection = self.env['woocommerce.connection'].browse(connection_id)
        
        existing = self.search([
            ('wc_coupon_id', '=', wc_data.get('id')),
            ('connection_id', '=', connection_id)
        ])
        
        if existing:
            existing._update_from_woocommerce_data(wc_data)
            return existing
        
        vals = {
            'name': wc_data.get('code', 'Coupon'),
            'code': wc_data.get('code', ''),
            'wc_coupon_id': wc_data.get('id'),
            'connection_id': connection_id,
            'sync_status': 'synced',
        }
        
        coupon = self.create(vals)
        coupon._update_from_woocommerce_data(wc_data)
        
        return coupon

