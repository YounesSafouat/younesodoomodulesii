from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class WooCommerceConflictResolutionWizard(models.TransientModel):
    _name = 'woocommerce.conflict.resolution.wizard'
    _description = 'WooCommerce Conflict Resolution Wizard'

    product_ids = fields.Many2many(
        'product.template',
        string='Products with Conflicts',
        readonly=True,
        help='Products that have synchronization conflicts'
    )
    
    resolution_method = fields.Selection([
        ('use_odoo', 'Use Odoo Data (Odoo Wins)'),
        ('use_woocommerce', 'Use WooCommerce Data (WooCommerce Wins)'),
        ('manual', 'Manual Review Required'),
    ], string='Resolution Method', default='use_odoo',
       help='Choose how to resolve conflicts')
    
    include_images = fields.Boolean(
        string='Include Images in Resolution',
        default=True,
        help='Whether to include image conflicts in the resolution'
    )
    
    auto_apply = fields.Boolean(
        string='Apply Resolution Automatically',
        default=False,
        help='Automatically apply the chosen resolution method'
    )
    
    conflict_details = fields.Html(
        string='Conflict Details',
        readonly=True,
        help='Detailed information about the conflicts'
    )

    @api.model
    def default_get(self, fields_list):
        """Set default values and populate conflict details"""
        res = super().default_get(fields_list)
        
        if 'product_ids' in fields_list and not res.get('product_ids'):
            product_ids = self.env.context.get('active_ids', [])
            if product_ids:
                res['product_ids'] = [(6, 0, product_ids)]
        
        if 'conflict_details' in fields_list:
            res['conflict_details'] = self._generate_conflict_details()
        
        return res

    def _generate_conflict_details(self):
        """Generate HTML details about conflicts"""
        if not self.product_ids:
            return '<p>No products with conflicts found.</p>'
        
        html = '<div class="o_warning">'
        html += '<h4>⚠️ Synchronization Conflicts Detected</h4>'
        html += '<p>The following products have conflicts between Odoo and WooCommerce:</p>'
        html += '<ul>'
        
        for product in self.product_ids:
            html += f'<li><strong>{product.name}</strong>'
            if product.wc_last_error:
                html += f'<br/><span style="color: red;">Error: {product.wc_last_error}</span>'
            html += '</li>'
        
        html += '</ul>'
        html += '<p><strong>Recommended Action:</strong> Choose a resolution method and apply it to resolve conflicts.</p>'
        html += '</div>'
        
        return html

    def action_resolve_conflicts(self):
        """Resolve conflicts based on selected method"""
        if not self.product_ids:
            raise ValidationError(_('No products selected for conflict resolution.'))
        
        resolved_count = 0
        error_count = 0
        error_messages = []
        
        for product in self.product_ids:
            try:
                if self.resolution_method == 'use_odoo':

                    product._sync_to_woocommerce()
                    resolved_count += 1
                    
                elif self.resolution_method == 'use_woocommerce':


                    product.write({
                        'wc_sync_status': 'synced',
                        'wc_last_error': False,
                    })
                    resolved_count += 1
                    
                elif self.resolution_method == 'manual':

                    product.write({
                        'wc_sync_status': 'conflict',
                        'wc_last_error': 'Requires manual review - conflict resolution wizard used',
                    })
                    resolved_count += 1
                
            except Exception as e:
                error_count += 1
                error_messages.append(f"{product.name}: {str(e)}")
                product.write({
                    'wc_sync_status': 'error',
                    'wc_last_error': str(e),
                })
        

        if error_count == 0:
            message = _('Successfully resolved conflicts for %d products.') % resolved_count
            message_type = 'success'
        else:
            message = _('Resolved conflicts for %d products, %d failed.') % (resolved_count, error_count)
            message_type = 'warning'
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Conflict Resolution Complete'),
                'message': message,
                'type': message_type,
                'sticky': error_count > 0,
                'details': '\n'.join(error_messages) if error_messages else None,
            }
        }

    def action_preview_conflicts(self):
        """Preview conflicts before resolution"""
        if not self.product_ids:
            raise ValidationError(_('No products selected.'))
        

        conflict_data = []
        for product in self.product_ids:
            conflict_data.append({
                'product_name': product.name,
                'odoo_price': product.list_price,
                'wc_price': 'N/A',
                'odoo_stock': getattr(product, 'qty_available', 0),
                'wc_stock': 'N/A',
                'last_sync': product.wc_last_sync,
                'error': product.wc_last_error,
            })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Conflict Preview'),
                'message': _('Found %d products with conflicts. Use "Resolve Conflicts" to fix them.') % len(conflict_data),
                'type': 'info',
                'sticky': False,
            }
        }

