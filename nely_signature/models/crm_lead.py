from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, MissingError
import logging
import re

_logger = logging.getLogger(__name__)

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    last_order = fields.Many2one('sale.order', string='Last Order', compute='_compute_last_order', store=True)
    last_order_state = fields.Char(string='Last Order State', readonly=True, compute='_compute_last_order', store=True)
        
    @api.depends('order_ids')
    def _compute_last_order(self):
        for rec in self:
            if rec.order_ids:
                rec.last_order = rec.order_ids.sorted(key=lambda o: o.create_date, reverse=True)[0]
                rec.last_order_state = rec.last_order.state
            else:
                rec.last_order = False
                rec.last_order_state = False

    def _sync_stage_with_order_state(self):
        """Synchronize CRM lead stage with sale order state"""
        for rec in self:
            if not rec.last_order_state:
                continue
                
            try:
                if rec.last_order_state == 'sale':
                    # Sale confirmed - move to "Won" stage
                    rec.stage_id = self.env.ref('crm.stage_lead4').id
                        
                elif rec.last_order_state == 'cancel':
                    # Sale cancelled - move to "Lost" stage
                    rec.stage_id = self.env.ref('__export__.crm_stage_8_53046ebf').id
                        
                elif rec.last_order_state == 'sent':
                    # Quotation sent - move to "Qualified" or "Proposal" stage
                    rec.stage_id = self.env.ref('crm.stage_lead2').id
                elif rec.last_order_state == 'draft':
                    rec.stage_id = self.env.ref('crm.stage_lead1').id
                        
            except Exception as e:
                _logger.warning(f"Failed to sync stage for lead {rec.id}: {str(e)}")

    

    @api.depends('last_order_state')
    def _onchange_order_ids(self):
        """Onchange method for UI updates"""
        self._sync_stage_with_order_state()

    def min_in_string(self, text):
        numbers = re.findall(r'\b\d{1,3}(?:\s\d{3})*(?:\s\d{3,})?\b', text)
        numbers = [int(number.replace(' ', '')) for number in numbers]
        if not numbers:
            return None  
        return min(map(int, numbers))

    def _prepare_opportunity_quotation_context(self):
        context = super()._prepare_opportunity_quotation_context()
        context['default_partner_invoice_id'] = self.partner_id.id
        if hasattr(self, 'x_studio_email_du_responsable_lgal'):
            if not self.x_studio_email_du_responsable_lgal:
                raise ValidationError(_("Veuillez fournir une adresse e-mail pour le responsable lgal"))
            else:
                if not self.x_studio_responsable_lgal.email:
                    self.x_studio_responsable_lgal.email = self.x_studio_email_du_responsable_lgal
                context['default_partner_id'] = self.x_studio_responsable_lgal.id
        
        context['default_partner_shipping_id'] = self.partner_id.id
        if hasattr(self, 'x_studio_boolean_field_5d4_1j4kpk674'):
            if self.x_studio_boolean_field_5d4_1j4kpk674:
                if (self.x_studio_nouveau_adresse):
                    context['default_partner_shipping_id'] = self.x_studio_nouveau_adresse.id
                else:
                    partner = self.env['res.partner'].create({
                        'name': self.x_studio_nom_et_prnom_1,
                        'street': self.x_studio_adresse,
                        'city': self.x_studio_ville,
                        'parent_id': self.partner_id.id,
                    })
                    context['default_partner_shipping_id'] = partner.id
     

        if hasattr(self, 'x_studio_renseigner_un_contact_spcifique_pour_la_livraison'):
            if self.x_studio_renseigner_un_contact_spcifique_pour_la_livraison:
                if self.x_studio_nouveau_contact:
                    self.partner_id.write({
                        'child_ids': [(4, self.x_studio_nouveau_contact.id)]
                    })
                else:
                    partner = self.env['res.partner'].create({
                        'name': self.x_studio_nom_et_prnom,
                        'phone': self.x_studio_tlphone,
                        'email': self.x_studio_email_1,
                        'parent_id': self.partner_id.id,
                    })
                    self.partner_id.write({
                        'child_ids': [(4, partner.id)]
                    })

        if hasattr(self, 'x_studio_mondataire'):
            if self.x_studio_mondataire:
                # context['default_partner_invoice_id'] = self.x_studio_mondataire.id
                context['default_sale_representative_id'] = self.x_studio_mondataire.id
                
        order_line_data = self.create_sale_order_line_data()
        prime_line = self.create_prime_line_data()
        if order_line_data:
            context['default_order_line'] = [(0, 0, order_line_data), (0, 0, prime_line)]

        return context

    def create_sale_order_line_data(self):
        """Create sale order line data structure (not actual record)"""
        self.ensure_one()
        product = self.env.company.signature_product_id
        
        if not product:
            return False
            
        return {
            'product_id': product.id,
            'product_uom_qty': self.x_studio_nombre_de_vlos_cargos or 1,
            'price_unit': product.lst_price,
        }
    def create_prime_line_data(self):
        """Create sale order line data structure (not actual record)"""
        self.ensure_one()
        product = self.env.company.prime_product_id
        sale_product = self.env.company.signature_product_id

        if not product:
            return False

        return {
            'product_id': product.id,
            'product_uom_qty':  1,
            'price_unit': (-1)* sale_product.lst_price*(self.x_studio_nombre_de_vlos_cargos or 1),

        }
