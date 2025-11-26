from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class WooCommerceCategoryMappingWizard(models.TransientModel):
    _name = 'woocommerce.category.mapping.wizard'
    _description = 'WooCommerce Category Mapping Wizard'

    wc_category_id = fields.Many2one(
        'woocommerce.category',
        string='WooCommerce Category',
        required=True,
        help='WooCommerce category to map'
    )
    
    connection_id = fields.Many2one(
        'woocommerce.connection',
        string='Connection',
        required=True,
        help='WooCommerce connection'
    )
    
    odoo_category_id = fields.Many2one(
        'product.category',
        string='Odoo Category',
        help='Select the Odoo category to map to this WooCommerce category'
    )
    
    create_new_category = fields.Boolean(
        string='Create New Odoo Category',
        help='Check to create a new Odoo category with the WooCommerce category name'
    )
    
    new_category_name = fields.Char(
        string='New Category Name',
        help='Name for the new Odoo category'
    )
    
    @api.model
    def default_get(self, fields_list):
        """Set default values"""
        res = super().default_get(fields_list)
        
        if 'wc_category_id' in self.env.context:
            wc_category = self.env['woocommerce.category'].browse(self.env.context['wc_category_id'])
            res['wc_category_id'] = wc_category.id
            res['connection_id'] = wc_category.connection_id.id
            res['new_category_name'] = wc_category.name
            
        return res
    
    @api.onchange('create_new_category')
    def _onchange_create_new_category(self):
        """Clear odoo_category_id when creating new category"""
        if self.create_new_category:
            self.odoo_category_id = False
        elif not self.odoo_category_id:

            if self.wc_category_id and self.wc_category_id.name:
                existing = self.env['product.category'].search([
                    ('name', 'ilike', self.wc_category_id.name)
                ], limit=1)
                if existing:
                    self.odoo_category_id = existing.id
    
    def action_map_category(self):
        """Map the WooCommerce category to Odoo category"""
        self.ensure_one()
        
        if not self.create_new_category and not self.odoo_category_id:
            raise UserError(_('Please select an Odoo category or choose to create a new one.'))
        
        if self.create_new_category:
            if not self.new_category_name:
                raise UserError(_('Please enter a name for the new category.'))
            

            odoo_category = self.env['product.category'].create({
                'name': self.new_category_name,
            })
            

            self.wc_category_id.write({
                'odoo_category_id': odoo_category.id,
            })
            
            message = _('Created new Odoo category "%s" and mapped it to WooCommerce category "%s".') % (
                self.new_category_name, self.wc_category_id.name)
        else:

            self.wc_category_id.write({
                'odoo_category_id': self.odoo_category_id.id,
            })
            
            message = _('Mapped WooCommerce category "%s" to Odoo category "%s".') % (
                self.wc_category_id.name, self.odoo_category_id.name)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Category Mapped'),
                'message': message,
                'type': 'success',
                'sticky': False,
            }
        }
    
    def action_bulk_map_categories(self):
        """Bulk map multiple WooCommerce categories"""

        unmapped_categories = self.env['woocommerce.category'].search([
            ('connection_id', '=', self.connection_id.id),
            ('odoo_category_id', '=', False)
        ])
        
        if not unmapped_categories:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Categories to Map'),
                    'message': _('All categories are already mapped.'),
                    'type': 'info',
                }
            }
        
        mapped_count = 0
        
        for wc_cat in unmapped_categories:

            existing = self.env['product.category'].search([
                ('name', 'ilike', wc_cat.name)
            ], limit=1)
            
            if existing:
                wc_cat.write({'odoo_category_id': existing.id})
                mapped_count += 1
            else:

                new_category = self.env['product.category'].create({
                    'name': wc_cat.name,
                })
                wc_cat.write({'odoo_category_id': new_category.id})
                mapped_count += 1
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Bulk Mapping Complete'),
                'message': _('Successfully mapped %d categories.') % mapped_count,
                'type': 'success',
                'sticky': False,
            }
        }

