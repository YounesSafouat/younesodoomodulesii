import json
import requests
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


class WooCommercePromotion(models.Model):
    _name = 'woocommerce.promotion'
    _description = 'WooCommerce Promotion'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, name'
    _rec_name = 'name'

    name = fields.Char(
        string='Promotion Name',
        required=True,
        help='Name of the promotion campaign'
    )
    
    connection_id = fields.Many2one(
        'woocommerce.connection',
        string='WooCommerce Connection',
        required=True,
        ondelete='cascade',
        help='WooCommerce connection'
    )
    
    description = fields.Text(
        string='Description',
        help='Promotion description'
    )
    
    discount_type = fields.Selection([
        ('percentage', 'Percentage Discount'),
        ('fixed', 'Fixed Amount Discount'),
    ], string='Discount Type', required=True, default='percentage',
       help='Type of discount to apply')
    
    discount_value = fields.Float(
        string='Discount Value',
        required=True,
        default=0.0,
        help='Discount amount. For percentage: enter percentage (e.g., 20 for 20%). For fixed: enter amount.'
    )
    
    date_start = fields.Datetime(
        string='Start Date',
        required=True,
        default=fields.Datetime.now,
        help='Promotion start date'
    )
    
    date_end = fields.Datetime(
        string='End Date',
        help='Promotion end date (leave empty for no expiration)'
    )
    
    product_ids = fields.Many2many(
        'product.template',
        'woocommerce_promotion_product_rel',
        'promotion_id', 'product_id',
        string='Products',
        help='Products included in this promotion'
    )
    
    product_category_ids = fields.Many2many(
        'product.category',
        'woocommerce_promotion_category_rel',
        'promotion_id', 'category_id',
        string='Product Categories',
        help='Product categories included in this promotion'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Uncheck to archive this promotion'
    )
    
    status = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('active', 'Active'),
        ('expired', 'Expired'),
    ], string='Status', compute='_compute_status', store=True,
       help='Current status of the promotion')
    
    is_active = fields.Boolean(
        string='Is Active',
        compute='_compute_is_active',
        store=True,
        help='Indicates if the promotion is currently active'
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
        help='Last time this promotion was synchronized'
    )
    
    product_count = fields.Integer(
        string='Product Count',
        compute='_compute_product_count',
        help='Number of products in this promotion'
    )
    
    @api.depends('date_start', 'date_end', 'active')
    def _compute_status(self):
        """Compute promotion status"""
        now = fields.Datetime.now()
        for promotion in self:
            if not promotion.active:
                promotion.status = 'draft'
            elif promotion.date_end and promotion.date_end < now:
                promotion.status = 'expired'
            elif promotion.date_start and promotion.date_start > now:
                promotion.status = 'scheduled'
            elif promotion.date_start and promotion.date_start <= now:
                if not promotion.date_end or promotion.date_end >= now:
                    promotion.status = 'active'
                else:
                    promotion.status = 'expired'
            else:
                promotion.status = 'draft'
    
    @api.depends('status', 'active')
    def _compute_is_active(self):
        """Compute if promotion is currently active"""
        for promotion in self:
            promotion.is_active = promotion.status == 'active' and promotion.active
    
    @api.depends('product_ids', 'product_category_ids')
    def _compute_product_count(self):
        """Compute total number of products in promotion"""
        for promotion in self:
            product_ids = promotion.product_ids.ids
            if promotion.product_category_ids:
                category_products = self.env['product.template'].search([
                    ('categ_id', 'in', promotion.product_category_ids.ids)
                ]).ids
                product_ids = list(set(product_ids + category_products))
            promotion.product_count = len(product_ids)
    
    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        """Ensure end date is after start date"""
        for promotion in self:
            if promotion.date_start and promotion.date_end:
                if promotion.date_end < promotion.date_start:
                    raise ValidationError(_('End date must be after start date.'))
    
    @api.constrains('discount_value', 'discount_type')
    def _check_discount_value(self):
        """Validate discount value"""
        for promotion in self:
            if promotion.discount_type == 'percentage':
                if promotion.discount_value < 0 or promotion.discount_value > 100:
                    raise ValidationError(_('Percentage discount must be between 0 and 100.'))
            elif promotion.discount_type == 'fixed':
                if promotion.discount_value < 0:
                    raise ValidationError(_('Fixed discount amount must be positive.'))
    
    def write(self, vals):
        """Override write to prevent changing sensitive fields and sync changes to WooCommerce"""
        sensitive_fields = ['connection_id']
        for field in sensitive_fields:
            if field in vals:
                for record in self:
                    if record[field] and vals[field] != record[field]:
                        raise UserError(_('Cannot change %s. This is a sensitive field that links the promotion to a WooCommerce connection. Changing it could break synchronization.') % field)

        result = super(WooCommercePromotion, self).write(vals)

        sync_fields = [
            'name', 'description', 'discount_type', 'discount_value',
            'date_start', 'date_end', 'active', 'product_ids', 'product_category_ids'
        ]

        if any(key in vals for key in sync_fields):
            for promotion in self:
                if promotion.connection_id:
                    try:
                        # If status is active, apply/update promotion. Otherwise, remove it.
                        if promotion.status == 'active':
                            promotion.action_apply_promotion()
                        else:
                            promotion.action_remove_promotion()
                    except Exception as e:
                        _logger.error(f"Error syncing promotion {promotion.name} to WooCommerce: {e}")
                        promotion.write({
                            'sync_status': 'error',
                            'sync_error': str(e)
                        })
        return result
    
    def action_apply_promotion(self):
        """Apply promotion to products by setting sale prices"""
        self.ensure_one()
        
        if not self.product_ids and not self.product_category_ids:
            raise UserError(_('Please select at least one product or category for this promotion.'))
        
        # Get all products
        product_ids = self.product_ids.ids
        if self.product_category_ids:
            category_products = self.env['product.template'].search([
                ('categ_id', 'in', self.product_category_ids.ids)
            ]).ids
            product_ids = list(set(product_ids + category_products))
        
        if not product_ids:
            raise UserError(_('No products found for this promotion.'))
        
        products = self.env['product.template'].browse(product_ids)
        updated_count = 0
        error_count = 0
        
        for product in products:
            try:
                # Find WooCommerce product for this connection
                wc_product = self.env['woocommerce.product'].search([
                    ('odoo_product_id', '=', product.id),
                    ('connection_id', '=', self.connection_id.id)
                ], limit=1)
                
                if not wc_product:
                    # Try to find by wc_product_id if product has one
                    if product.wc_product_id:
                        wc_product = self.env['woocommerce.product'].search([
                            ('wc_product_id', '=', product.wc_product_id),
                            ('connection_id', '=', self.connection_id.id)
                        ], limit=1)
                
                if not wc_product:
                    _logger.warning(f"No WooCommerce product found for {product.name} in connection {self.connection_id.name}")
                    error_count += 1
                    continue
                
                # Get regular price (use WooCommerce regular_price or Odoo list_price)
                regular_price = wc_product.regular_price if wc_product.regular_price > 0 else product.list_price
                
                # Calculate sale price
                if self.discount_type == 'percentage':
                    sale_price = regular_price * (1 - self.discount_value / 100)
                else:  # fixed
                    sale_price = max(0, regular_price - self.discount_value)
                
                # Update WooCommerce product sale price
                wc_product.write({'sale_price': sale_price})
                
                # Sync to WooCommerce
                try:
                    wc_product._sync_to_woocommerce_store()
                    updated_count += 1
                except Exception as e:
                    _logger.error(f"Error syncing product {product.name} to WooCommerce: {e}")
                    error_count += 1
                    
            except Exception as e:
                _logger.error(f"Error applying promotion to product {product.name}: {e}")
                error_count += 1
        
        message = _('Promotion applied to %d products.') % updated_count
        if error_count > 0:
            message += _(' %d errors occurred.') % error_count
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Promotion Applied'),
                'message': message,
                'type': 'success' if error_count == 0 else 'warning',
                'sticky': False,
            }
        }
    
    def action_remove_promotion(self):
        """Remove promotion by restoring original prices"""
        self.ensure_one()
        
        # Get all products
        product_ids = self.product_ids.ids
        if self.product_category_ids:
            category_products = self.env['product.template'].search([
                ('categ_id', 'in', self.product_category_ids.ids)
            ]).ids
            product_ids = list(set(product_ids + category_products))
        
        if not product_ids:
            raise UserError(_('No products found for this promotion.'))
        
        products = self.env['product.template'].browse(product_ids)
        updated_count = 0
        
        for product in products:
            try:
                # Find WooCommerce product for this connection
                wc_product = self.env['woocommerce.product'].search([
                    ('odoo_product_id', '=', product.id),
                    ('connection_id', '=', self.connection_id.id)
                ], limit=1)
                
                if not wc_product:
                    # Try to find by wc_product_id if product has one
                    if product.wc_product_id:
                        wc_product = self.env['woocommerce.product'].search([
                            ('wc_product_id', '=', product.wc_product_id),
                            ('connection_id', '=', self.connection_id.id)
                        ], limit=1)
                
                if not wc_product:
                    _logger.warning(f"No WooCommerce product found for {product.name} in connection {self.connection_id.name}")
                    continue
                
                # Remove sale price (set to 0 or empty)
                wc_product.write({'sale_price': 0})
                
                # Sync to WooCommerce
                try:
                    wc_product._sync_to_woocommerce_store()
                    updated_count += 1
                except Exception as e:
                    _logger.error(f"Error syncing product {product.name} to WooCommerce: {e}")
                    
            except Exception as e:
                _logger.error(f"Error removing promotion from product {product.name}: {e}")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Promotion Removed'),
                'message': _('Promotion removed from %d products.') % updated_count,
                'type': 'success',
                'sticky': False,
            }
        }
    
    def action_sync_to_woocommerce(self):
        """Sync promotion to WooCommerce by applying sale prices"""
        self.ensure_one()
        try:
            result = self.action_apply_promotion()
            self.write({
                'sync_status': 'synced',
                'last_sync': fields.Datetime.now(),
                'sync_error': False,
            })
            return result
        except Exception as e:
            _logger.error(f"Error syncing promotion {self.name} to WooCommerce: {e}")
            self.write({
                'sync_status': 'error',
                'sync_error': str(e)
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Failed to sync promotion to WooCommerce: %s') % str(e),
                    'type': 'danger',
                }
            }

