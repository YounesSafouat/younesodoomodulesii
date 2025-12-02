# -*- coding: utf-8 -*-

import logging
import requests
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    #fields 
    stripe_payment_link_id = fields.Char(
        string='Stripe Payment Link ID', 
        readonly=True,
        help='The Stripe Payment Link ID returned from Stripe API'
    )
    
    stripe_payment_link_url = fields.Char(
        string='Stripe Payment Link URL', 
        readonly=True,
        help='The URL that customers can use to pay'
    )
    
    stripe_payment_link_status = fields.Selection(
        string='Payment Link Status',
        selection=[
            ('created', 'Created'),
            ('paid', 'Paid'),
            ('expired', 'Expired'),
            ('canceled', 'Canceled')
        ],
        readonly=True,
        help='Current status of the Stripe payment link'
    )
    
    stripe_payment_link_active = fields.Boolean(
        string='Payment Link Active',
        readonly=True,
        help='Whether the payment link is currently active'
    )
    
    stripe_payment_link_currency = fields.Char(
        string='Payment Link Currency',
        readonly=True,
        help='Currency code (e.g., usd, eur)'
    )
    
   
    
    stripe_payment_link_created = fields.Datetime(
        string='Payment Link Created', 
        readonly=True
    )
    
    stripe_customer_email = fields.Char(
        string='Customer Email (from Stripe)', 
        readonly=True,
        help='Email address provided by customer during Stripe payment'
    )
    
    stripe_customer_name = fields.Char(
        string='Customer Name (from Stripe)', 
        readonly=True
    )
    
    stripe_customer_address_line1 = fields.Char(
        string='Address Line 1 (from Stripe)', 
        readonly=True
    )
    
    stripe_customer_address_line2 = fields.Char(
        string='Address Line 2 (from Stripe)', 
        readonly=True
    )
    
    stripe_customer_city = fields.Char(
        string='City (from Stripe)', 
        readonly=True
    )
    
    stripe_customer_postal_code = fields.Char(
        string='Postal Code (from Stripe)', 
        readonly=True
    )
    
    stripe_customer_country = fields.Char(
        string='Country (from Stripe)', 
        readonly=True
    )
    
    stripe_payment_succeeded = fields.Boolean(
        string='Payment Succeeded', 
        readonly=True,
        default=False,
        help='True when payment has been successfully completed'
    )
    
    stripe_invoice_id = fields.Char(
        string='Stripe Invoice ID',
        readonly=True,
        help='The Stripe Invoice ID created from the payment link'
    )
    
    stripe_hosted_invoice_url = fields.Char(
        string='Stripe Hosted Invoice URL',
        readonly=True,
        help='The hosted invoice URL where customers can view and pay their invoice'
    )




    #methods stripe
    def action_generate_stripe_payment_link(self):
        """
        Generate a Stripe Payment Link for this sale order.
        This method:
        1. Gets Stripe API key from settings
        2. Builds line items from sale order
        3. Creates payment link via Stripe API
        4. Stores the payment link URL and data
        """
        self.ensure_one()
        
        if self.stripe_payment_link_id:
            raise UserError(_('A payment link already exists for this quotation. Please use the existing link.'))
        
        
        stripe_api_key = self.env['ir.config_parameter'].sudo().get_param('stripe_integration.api_key')
        
        if not stripe_api_key:
            raise UserError(_('Stripe API key is not configured. Please configure it in Settings > Stripe Integration.'))
        
        stripe_api_key = stripe_api_key.strip()
        if stripe_api_key.startswith('pk_'):
            raise UserError(_(
                'Invalid Stripe API key: You are using a publishable key (pk_*). '
                'Please use a secret key (sk_test_* or sk_live_*) instead. '
                'Get your secret key from: https://dashboard.stripe.com/apikeys'
            ))
        if not stripe_api_key.startswith('sk_'):
            raise UserError(_(
                'Invalid Stripe API key format. The key should start with "sk_test_" (for test mode) '
                'or "sk_live_" (for live mode). Get your secret key from: https://dashboard.stripe.com/apikeys'
            ))
        
        line_items = []
        for line in self.order_line:
            if not line.display_type:  
                line_items.append({
                    'price_data': {
                        'currency': self.currency_id.name.lower(),
                        'product_data': {
                            'name': line.name or line.product_id.name or 'Product',
                            'description': line.name or '',
                        },
                        'unit_amount': int(line.price_unit * 100), 
                    },
                    'quantity': int(line.product_uom_qty),
                })
        
        if not line_items:
            raise UserError(_('Cannot create payment link: No products in this quotation.'))
        
        url = 'https://api.stripe.com/v1/payment_links'
        
       
        data = {}
        for index, item in enumerate(line_items):
            prefix = f'line_items[{index}]'
            
            price_data = item.get('price_data', {})
            data[f'{prefix}[price_data][currency]'] = price_data.get('currency', 'usd')
            data[f'{prefix}[price_data][unit_amount]'] = price_data.get('unit_amount')
            
            product_data = price_data.get('product_data', {})
            if product_data.get('name'):
                data[f'{prefix}[price_data][product_data][name]'] = product_data.get('name')
            if product_data.get('description'):
                data[f'{prefix}[price_data][product_data][description]'] = product_data.get('description')
            
            data[f'{prefix}[quantity]'] = item.get('quantity', 1)
        
        data['invoice_creation[enabled]'] = 'true'
        
        try:
            response = requests.post(
                url,
                headers={
                    'Authorization': f'Bearer {stripe_api_key}',
                },
                data=data, 
                timeout=30
            )
            
            if response.status_code == 403:
                try:
                    error_data = response.json()
                    error_message = error_data.get('error', {}).get('message', 'Forbidden')
                    _logger.error(f'Stripe API 403 Forbidden: {error_message}. Response: {response.text}')
                    raise UserError(_(
                        'Stripe API authentication failed (403 Forbidden). '
                        'Please verify that:\n'
                        '1. You are using a Secret API Key (starts with sk_test_ or sk_live_)\n'
                        '2. The API key is correct and not expired\n'
                        '3. The API key has the necessary permissions\n'
                        'Error details: %s'
                    ) % error_message)
                except (ValueError, KeyError):
                    _logger.error(f'Stripe API 403 Forbidden. Response: {response.text}')
                    raise UserError(_(
                        'Stripe API authentication failed (403 Forbidden). '
                        'Please verify your API key in Settings > Stripe Integration. '
                        'Make sure you are using a Secret API Key (sk_test_* or sk_live_*), '
                        'not a Publishable Key (pk_*).'
                    ))
            
            response.raise_for_status()  
            result = response.json()
            
            self.write({
                'stripe_payment_link_id': result.get('id'),
                'stripe_payment_link_url': result.get('url'),
                'stripe_payment_link_active': result.get('active', False),
                'stripe_payment_link_currency': result.get('currency'),
                'stripe_payment_link_created': fields.Datetime.now(),
                'stripe_payment_link_status': 'created',
            })
            
            _logger.info(f'Stripe payment link created for sale order {self.name}: {result.get("url")}')
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Payment link created successfully! URL: %s') % result.get('url'),
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except requests.exceptions.RequestException as e:
            _logger.error(f'Error creating Stripe payment link: {str(e)}')
            raise UserError(_('Error creating Stripe payment link: %s') % str(e))
        except Exception as e:
            _logger.error(f'Unexpected error creating Stripe payment link: {str(e)}')
            raise UserError(_('Unexpected error: %s') % str(e))
    
    def action_open_stripe_payment_link(self):
        """Open the Stripe payment link in a new window"""
        self.ensure_one()
        
        if not self.stripe_payment_link_url:
            raise UserError(_('No payment link available for this quotation.'))
        
        return {
            'type': 'ir.actions.act_url',
            'url': self.stripe_payment_link_url,
            'target': 'new',
        }
    
    def action_open_stripe_invoice(self):
        """Open the Stripe hosted invoice URL in a new window"""
        self.ensure_one()
        
        if not self.stripe_hosted_invoice_url:
            raise UserError(_('No hosted invoice URL available for this quotation.'))
        
        return {
            'type': 'ir.actions.act_url',
            'url': self.stripe_hosted_invoice_url,
            'target': 'new',
        }
    
    def _find_mail_template(self):
        """Override to use custom template with Stripe payment button"""
        # Get the original template
        mail_template = super()._find_mail_template()
        
        # If we have a Stripe payment link or need payment, use our custom template
        if self.stripe_payment_link_url or self._has_to_be_paid():
            custom_template = self.env.ref('stripe_integration.email_template_edi_sale_stripe', raise_if_not_found=False)
            if custom_template:
                return custom_template
        
        return mail_template    