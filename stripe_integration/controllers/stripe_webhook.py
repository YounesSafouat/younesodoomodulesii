# -*- coding: utf-8 -*-

import json
import logging
import hmac
import hashlib
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class StripeWebhookController(http.Controller):
    """Controller to handle Stripe webhooks"""
    
    @http.route('/stripe/webhook', type='http', auth='public', methods=['POST'], csrf=False)
    def stripe_webhook(self):
        """
        Handle Stripe webhook notifications.
        Stripe sends events when payments are completed.
        """
        try:
            raw_data = request.httprequest.get_data()
            signature = request.httprequest.headers.get('Stripe-Signature')
            
            _logger.info(f"🔔 Stripe webhook received")
            
            try:
                webhook_data = json.loads(raw_data)
            except json.JSONDecodeError:
                _logger.error("❌ Invalid JSON in webhook data")
                return request.make_response("Invalid JSON", status=400)
            
            event_type = webhook_data.get('type')
            event_data = webhook_data.get('data', {}).get('object', {})
            
            _logger.info(f"🔔 Stripe webhook event: {event_type}")
            
            if event_type == 'checkout.session.completed':
                _logger.info("✅ Payment completed via Stripe")
                self._handle_checkout_completed(event_data)
            
            elif event_type == 'payment_intent.succeeded':
                _logger.info("✅ Payment intent succeeded")
                self._handle_payment_intent_succeeded(event_data)
            
            else:
                _logger.info(f"ℹ️ Unhandled event type: {event_type}")
            
            return request.make_response("OK", status=200)
            
        except Exception as e:
            _logger.error(f"❌ Stripe webhook error: {str(e)}")
            return request.make_response("Internal Server Error", status=500)
    
    def _handle_checkout_completed(self, session_data):
        """
        Handle checkout.session.completed event.
        This is triggered when a customer completes payment via a payment link.
        """
        try:
            payment_link_id = session_data.get('payment_link')
            
            if not payment_link_id:
                _logger.warning("⚠️ No payment link ID in checkout session")
                return
            
            sale_order = request.env['sale.order'].sudo().search([
                ('stripe_payment_link_id', '=', payment_link_id)
            ], limit=1)
            
            if not sale_order:
                _logger.warning(f"⚠️ No sale order found for payment link: {payment_link_id}")
                return
            
            customer_details = session_data.get('customer_details', {})
            customer_email = customer_details.get('email')
            customer_name = customer_details.get('name')
            
            address = customer_details.get('address', {})
            address_line1 = address.get('line1')
            address_line2 = address.get('line2')
            city = address.get('city')
            postal_code = address.get('postal_code')
            country = address.get('country')
            
            sale_order.write({
                'stripe_payment_link_status': 'paid',
                'stripe_payment_succeeded': True,
                'stripe_customer_email': customer_email,
                'stripe_customer_name': customer_name,
                'stripe_customer_address_line1': address_line1,
                'stripe_customer_address_line2': address_line2,
                'stripe_customer_city': city,
                'stripe_customer_postal_code': postal_code,
                'stripe_customer_country': country,
            })
            
            _logger.info(f"✅ Updated sale order {sale_order.name} with payment information")
            
            if sale_order.partner_id and customer_email:
                partner_updates = {}
                
                if customer_email and (not sale_order.partner_id.email or sale_order.partner_id.email != customer_email):
                    partner_updates['email'] = customer_email
                
                if customer_name and sale_order.partner_id.name != customer_name:
                    partner_updates['name'] = customer_name
                
                if address_line1:
                    if not sale_order.partner_id.street or sale_order.partner_id.street != address_line1:
                        partner_updates['street'] = address_line1
                
                if address_line2:
                    if not sale_order.partner_id.street2 or sale_order.partner_id.street2 != address_line2:
                        partner_updates['street2'] = address_line2
                
                if city:
                    if not sale_order.partner_id.city or sale_order.partner_id.city != city:
                        partner_updates['city'] = city
                
                if postal_code:
                    if not sale_order.partner_id.zip or sale_order.partner_id.zip != postal_code:
                        partner_updates['zip'] = postal_code
                
                if country:
                    country_obj = request.env['res.country'].sudo().search([
                        ('code', '=', country.upper())
                    ], limit=1)
                    if country_obj and sale_order.partner_id.country_id != country_obj:
                        partner_updates['country_id'] = country_obj.id
                
                if partner_updates:
                    sale_order.partner_id.write(partner_updates)
                    _logger.info(f"✅ Updated customer {sale_order.partner_id.name} with information from Stripe")
            
        except Exception as e:
            _logger.error(f"❌ Error handling checkout completed: {str(e)}")
            raise
    
    def _handle_payment_intent_succeeded(self, payment_intent_data):
        """
        Handle payment_intent.succeeded event (backup method).
        This might be used if checkout.session.completed doesn't fire.
        """
        _logger.info("Payment intent succeeded - this is a backup handler")
        pass
    
    @http.route('/stripe/webhook/test', type='http', auth='public', methods=['GET'], csrf=False)
    def stripe_webhook_test(self):
        """Test webhook endpoint"""
        return request.make_response("Stripe webhook endpoint is working!", status=200)