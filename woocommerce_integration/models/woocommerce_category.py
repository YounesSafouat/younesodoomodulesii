from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class WooCommerceCategory(models.Model):
    _name = 'woocommerce.category'
    _description = 'WooCommerce Product Category Mapping'
    _order = 'name'

    name = fields.Char(
        string='Category Name',
        required=True,
        help='Name of the category from WooCommerce'
    )
    
    wc_category_id = fields.Integer(
        string='WooCommerce Category ID',
        required=True,
        help='Category ID in WooCommerce'
    )
    
    connection_id = fields.Many2one(
        'woocommerce.connection',
        string='WooCommerce Connection',
        required=True,
        ondelete='cascade',
        help='WooCommerce connection this category belongs to'
    )
    
    odoo_category_id = fields.Many2one(
        'product.category',
        string='Odoo Category',
        help='Mapped Odoo product category'
    )
    
    wc_slug = fields.Char(
        string='WooCommerce Slug',
        help='Category slug in WooCommerce'
    )
    
    wc_parent_id = fields.Integer(
        string='WooCommerce Parent ID',
        help='Parent category ID in WooCommerce'
    )
    
    parent_id = fields.Many2one(
        'woocommerce.category',
        string='Parent Category',
        help='Parent category in the mapping'
    )
    
    description = fields.Text(
        string='Description',
        help='Category description from WooCommerce'
    )
    
    wc_image_url = fields.Char(
        string='WooCommerce Image URL',
        help='Category image URL from WooCommerce'
    )
    
    wc_count = fields.Integer(
        string='Product Count',
        help='Number of products in this category in WooCommerce'
    )
    
    sync_status = fields.Selection([
        ('synced', 'Synced'),
        ('pending', 'Pending'),
        ('error', 'Error'),
    ], string='Sync Status', default='synced', readonly=True)
    
    last_sync = fields.Datetime(
        string='Last Sync',
        readonly=True,
        help='Last time this category was synced'
    )
    
    _sql_constraints = [
        ('wc_category_unique', 'unique(wc_category_id, connection_id)',
         'WooCommerce category must be unique per connection!')
    ]
    
    def name_get(self):
        """Custom name display"""
        result = []
        for category in self:
            name = f"{category.name}"
            if category.odoo_category_id:
                name += f" → {category.odoo_category_id.name}"
            result.append((category.id, name))
        return result
    
    def action_map_to_odoo_category(self):
        """Open wizard to map this WooCommerce category to an Odoo category"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Map to Odoo Category'),
            'res_model': 'woocommerce.category.mapping.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_wc_category_id': self.id,
                'default_connection_id': self.connection_id.id,
            }
        }
    
    def action_sync_from_woocommerce(self):
        """Sync category data from WooCommerce"""
        self.ensure_one()
        try:
            category_data = self.connection_id.get_category(self.wc_category_id)
            if category_data:
                self._update_from_woocommerce_data(category_data)
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Category synced successfully from WooCommerce'),
                        'type': 'success',
                        'sticky': False,
                    }
                }
        except Exception as e:
            _logger.error(f"Error syncing category from WooCommerce: {str(e)}")
            raise UserError(_('Error syncing category: %s') % str(e))
    
    def _update_from_woocommerce_data(self, category_data):
        """Update category fields from WooCommerce data"""
        self.ensure_one()
        
        vals = {
            'name': category_data.get('name', ''),
            'wc_slug': category_data.get('slug', ''),
            'description': category_data.get('description', ''),
            'wc_count': category_data.get('count', 0),
            'wc_parent_id': category_data.get('parent', 0),
            'last_sync': fields.Datetime.now(),
            'sync_status': 'synced',
        }
        
        if category_data.get('image'):
            vals['wc_image_url'] = category_data['image'].get('src', '')
        
        self.write(vals)
        
        # Update parent relationship
        if vals['wc_parent_id']:
            parent = self.search([
                ('wc_category_id', '=', vals['wc_parent_id']),
                ('connection_id', '=', self.connection_id.id)
            ], limit=1)
            if parent:
                self.write({'parent_id': parent.id})


class ProductCategory(models.Model):
    _inherit = 'product.category'
    
    wc_category_ids = fields.One2many(
        'woocommerce.category',
        'odoo_category_id',
        string='WooCommerce Categories',
        help='WooCommerce categories mapped to this Odoo category'
    )
    
    wc_category_count = fields.Integer(
        string='WooCommerce Categories',
        compute='_compute_wc_category_count'
    )
    
    @api.depends('wc_category_ids')
    def _compute_wc_category_count(self):
        for category in self:
            category.wc_category_count = len(category.wc_category_ids)


