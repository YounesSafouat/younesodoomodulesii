from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class WooCommerceVariantMapping(models.Model):
    """Maps WooCommerce product variations to Odoo product variants"""
    _name = 'woocommerce.variant.mapping'
    _description = 'WooCommerce Variant Mapping'
    _order = 'product_id, wc_variation_id'

    name = fields.Char(
        string='Variant Name',
        compute='_compute_name',
        store=True,
        help='Display name for this variant mapping'
    )
    
    product_id = fields.Many2one(
        'woocommerce.product',
        string='WooCommerce Product',
        required=True,
        ondelete='cascade',
        help='Parent WooCommerce product'
    )
    
    connection_id = fields.Many2one(
        'woocommerce.connection',
        related='product_id.connection_id',
        store=True,
        readonly=True,
        help='WooCommerce connection'
    )
    
    wc_variation_id = fields.Integer(
        string='WooCommerce Variation ID',
        required=True,
        help='Variation ID in WooCommerce'
    )
    
    odoo_variant_id = fields.Many2one(
        'product.product',
        string='Odoo Variant',
        help='Corresponding Odoo product variant'
    )
    
    odoo_product_template_id = fields.Many2one(
        'product.template',
        related='odoo_variant_id.product_tmpl_id',
        store=True,
        readonly=True,
        help='Odoo product template'
    )
    
    wc_sku = fields.Char(
        string='WooCommerce SKU',
        help='SKU for this variation'
    )
    
    wc_price = fields.Float(
        string='WooCommerce Price',
        help='Price for this variation'
    )
    
    wc_regular_price = fields.Float(
        string='WooCommerce Regular Price',
        help='Regular price for this variation'
    )
    
    wc_sale_price = fields.Float(
        string='WooCommerce Sale Price',
        help='Sale price for this variation'
    )
    
    wc_stock_quantity = fields.Float(
        string='WooCommerce Stock',
        help='Stock quantity for this variation'
    )
    
    wc_stock_status = fields.Selection([
        ('instock', 'In Stock'),
        ('outofstock', 'Out of Stock'),
        ('onbackorder', 'On Backorder'),
    ], string='WooCommerce Stock Status')
    
    wc_variation_data = fields.Text(
        string='WooCommerce Variation Data',
        help='Raw JSON data from WooCommerce for this variation'
    )
    
    attribute_values = fields.Text(
        string='Attribute Values',
        help='Attribute values for this variation (JSON format)'
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
        help='Last time this variant was synchronized'
    )
    
    _sql_constraints = [
        ('wc_variation_unique', 'unique(product_id, wc_variation_id)',
         'WooCommerce variation must be unique per product!')
    ]
    
    @api.depends('wc_variation_id', 'odoo_variant_id', 'attribute_values')
    def _compute_name(self):
        """Compute variant name from attributes"""
        for record in self:
            if record.odoo_variant_id:
                record.name = record.odoo_variant_id.display_name
            elif record.attribute_values:
                try:
                    import json
                    attrs = json.loads(record.attribute_values)
                    attr_names = [f"{k}: {v}" for k, v in attrs.items()]
                    record.name = f"Variation {record.wc_variation_id} ({', '.join(attr_names)})"
                except:
                    record.name = f"Variation {record.wc_variation_id}"
            else:
                record.name = f"Variation {record.wc_variation_id}"
    
    def action_create_odoo_variant(self):
        """Create Odoo product variant from WooCommerce variation"""
        self.ensure_one()
        
        if not self.product_id.odoo_product_id:
            raise UserError(_('Please create the Odoo product template first before creating variants.'))
        
        try:
            import json
            

            attr_values = {}
            if self.attribute_values:
                attr_values = json.loads(self.attribute_values)
            

            product_template = self.product_id.odoo_product_id
            attribute_line_ids = []
            
            for attr_name, attr_value in attr_values.items():

                attribute = self.env['product.attribute'].search([
                    ('name', '=', attr_name)
                ], limit=1)
                
                if not attribute:
                    attribute = self.env['product.attribute'].create({
                        'name': attr_name,
                        'create_variant': 'always',
                    })
                

                attr_value_record = self.env['product.attribute.value'].search([
                    ('name', '=', attr_value),
                    ('attribute_id', '=', attribute.id)
                ], limit=1)
                
                if not attr_value_record:
                    attr_value_record = self.env['product.attribute.value'].create({
                        'name': attr_value,
                        'attribute_id': attribute.id,
                    })
                

                attr_line = product_template.attribute_line_ids.filtered(
                    lambda l: l.attribute_id.id == attribute.id
                )
                
                if not attr_line:

                    self.env['product.template.attribute.line'].create({
                        'product_tmpl_id': product_template.id,
                        'attribute_id': attribute.id,
                        'value_ids': [(6, 0, [attr_value_record.id])],
                    })
                else:

                    if attr_value_record.id not in attr_line.value_ids.ids:
                        attr_line.value_ids = [(4, attr_value_record.id)]
            

            product_template._create_product_variant_ids()
            

            variant = self._find_matching_variant(product_template, attr_values)
            
            if variant:
                self.odoo_variant_id = variant.id
                

                variant_vals = {}
                if self.wc_sku:
                    variant_vals['default_code'] = self.wc_sku
                if self.wc_sale_price and self.wc_sale_price > 0:
                    variant_vals['list_price'] = self.wc_sale_price
                elif self.wc_regular_price and self.wc_regular_price > 0:
                    variant_vals['list_price'] = self.wc_regular_price
                elif self.wc_price and self.wc_price > 0:
                    variant_vals['list_price'] = self.wc_price
                
                if variant_vals:
                    variant.write(variant_vals)
                

                if self.wc_stock_quantity is not None:

                    if hasattr(variant, 'qty_available'):

                        pass
                
                self.write({
                    'sync_status': 'synced',
                    'last_sync': fields.Datetime.now(),
                })
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Variant created successfully!'),
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_('Could not find or create matching variant. Please check attribute values.'))
                
        except Exception as e:
            _logger.error(f"Error creating variant: {e}")
            self.write({
                'sync_status': 'error',
                'sync_error': str(e),
            })
            raise UserError(_('Failed to create variant: %s') % str(e))
    
    def _find_matching_variant(self, product_template, attr_values):
        """Find Odoo variant that matches the attribute values"""
        for variant in product_template.product_variant_ids:
            variant_attrs = {}
            for attr_line in variant.product_template_attribute_value_ids:
                variant_attrs[attr_line.attribute_id.name] = attr_line.name
            

            if all(variant_attrs.get(k) == v for k, v in attr_values.items()):
                return variant
        
        return False
    
    def action_sync_to_woocommerce(self):
        """Sync variant changes to WooCommerce"""
        self.ensure_one()
        
        if not self.odoo_variant_id:
            raise UserError(_('No Odoo variant linked to sync.'))
        
        try:

            variation_data = {
                'sku': self.odoo_variant_id.default_code or '',
                'regular_price': str(self.odoo_variant_id.list_price or '0.00'),
            }
            

            if self.wc_sale_price and self.wc_sale_price > 0:
                variation_data['sale_price'] = str(self.wc_sale_price)
            else:
                variation_data['sale_price'] = ''
            

            if hasattr(self.odoo_variant_id, 'qty_available'):
                variation_data['stock_quantity'] = int(self.odoo_variant_id.qty_available or 0)
                variation_data['manage_stock'] = True
            

            connection = self.product_id.connection_id
            url = connection._get_api_url(f'products/{self.product_id.wc_product_id}/variations/{self.wc_variation_id}')
            headers = connection._get_auth_headers()
            
            import requests
            response = requests.put(url, headers=headers, json=variation_data, timeout=600)
            response.raise_for_status()
            
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
                    'message': _('Variant synced to WooCommerce successfully!'),
                    'type': 'success',
                }
            }
            
        except Exception as e:
            _logger.error(f"Error syncing variant to WooCommerce: {e}")
            self.write({
                'sync_status': 'error',
                'sync_error': str(e),
            })
            raise UserError(_('Failed to sync variant: %s') % str(e))
    
    def action_sync_from_woocommerce(self):
        """Sync variant data from WooCommerce"""
        self.ensure_one()
        
        try:
            connection = self.product_id.connection_id
            url = connection._get_api_url(f'products/{self.product_id.wc_product_id}/variations/{self.wc_variation_id}')
            headers = connection._get_auth_headers()
            
            import requests
            response = requests.get(url, headers=headers, timeout=600)
            response.raise_for_status()
            
            variation_data = response.json()
            

            self.write({
                'wc_sku': variation_data.get('sku', ''),
                'wc_price': float(variation_data.get('price', 0)),
                'wc_regular_price': float(variation_data.get('regular_price', 0)),
                'wc_sale_price': float(variation_data.get('sale_price', 0)) if variation_data.get('sale_price') else 0,
                'wc_stock_quantity': float(variation_data.get('stock_quantity', 0)),
                'wc_stock_status': variation_data.get('stock_status', 'instock'),
                'wc_variation_data': str(variation_data),
                'sync_status': 'synced',
                'last_sync': fields.Datetime.now(),
                'sync_error': False,
            })
            

            if self.odoo_variant_id:
                variant_vals = {}
                if self.wc_sale_price and self.wc_sale_price > 0:
                    variant_vals['list_price'] = self.wc_sale_price
                elif self.wc_regular_price and self.wc_regular_price > 0:
                    variant_vals['list_price'] = self.wc_regular_price
                
                if variant_vals:
                    self.odoo_variant_id.write(variant_vals)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Variant synced from WooCommerce successfully!'),
                    'type': 'success',
                }
            }
            
        except Exception as e:
            _logger.error(f"Error syncing variant from WooCommerce: {e}")
            self.write({
                'sync_status': 'error',
                'sync_error': str(e),
            })
            raise UserError(_('Failed to sync variant: %s') % str(e))
    
    def action_view_odoo_variant(self):
        """View the corresponding Odoo variant"""
        self.ensure_one()
        
        if not self.odoo_variant_id:
            raise UserError(_('No Odoo variant linked to this variation.'))
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product.product',
            'res_id': self.odoo_variant_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    @api.model
    def create_from_woocommerce_variation(self, variation_data, product_id):
        """Create variant mapping from WooCommerce variation data"""
        try:
            import json
            

            attributes = variation_data.get('attributes', [])
            attr_values = {}
            for attr in attributes:
                attr_name = attr.get('name', '')
                attr_value = attr.get('option', '')
                if attr_name and attr_value:
                    attr_values[attr_name] = attr_value
            

            existing = self.search([
                ('product_id', '=', product_id),
                ('wc_variation_id', '=', variation_data.get('id'))
            ], limit=1)
            
            if existing:
                return existing
            
            vals = {
                'product_id': product_id,
                'wc_variation_id': variation_data.get('id'),
                'wc_sku': variation_data.get('sku', ''),
                'wc_price': float(variation_data.get('price', 0)),
                'wc_regular_price': float(variation_data.get('regular_price', 0)),
                'wc_sale_price': float(variation_data.get('sale_price', 0)) if variation_data.get('sale_price') else 0,
                'wc_stock_quantity': float(variation_data.get('stock_quantity', 0)),
                'wc_stock_status': variation_data.get('stock_status', 'instock'),
                'wc_variation_data': str(variation_data),
                'attribute_values': json.dumps(attr_values),
                'sync_status': 'pending',
            }
            
            return self.create(vals)
            
        except Exception as e:
            _logger.error(f"Error creating variant mapping: {e}")
            raise



