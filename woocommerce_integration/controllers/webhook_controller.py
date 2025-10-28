# -*- coding: utf-8 -*-

import json
import logging
import hmac
import hashlib
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class WooCommerceWebhookController(http.Controller):
    
    @http.route('/woocommerce/webhook/<int:webhook_id>', type='http', auth='public', methods=['POST', 'GET'], csrf=False)
    def webhook_handler(self, webhook_id, **kwargs):
        """Handle incoming WooCommerce webhooks"""
        _logger.info(f'Webhook controller called with webhook_id: {webhook_id}')
        try:
            # Get webhook configuration
            webhook = request.env['woocommerce.order.webhook'].browse(webhook_id)
            if not webhook.exists() or not webhook.active:
                _logger.warning(f'Webhook {webhook_id} not found or inactive')
                return request.make_response('Webhook not found or inactive', status=404)
            
            # Verify webhook signature if secret is configured
            if webhook.webhook_secret:
                # Only verify signature if it's provided in headers
                signature_header = request.httprequest.headers.get('X-WC-Webhook-Signature')
                if signature_header:
                    if not self._verify_webhook_signature(request.httprequest, webhook.webhook_secret):
                        _logger.warning(f'Invalid webhook signature for webhook {webhook_id}')
                        return request.make_response('Invalid webhook signature', status=403)
                else:
                    # If secret is set but no signature provided, accept the request for testing
                    _logger.info(f'Webhook secret configured but no signature provided, accepting for testing')
            
            # Handle GET requests (webhook testing)
            if request.httprequest.method == 'GET':
                return request.make_response(
                    json.dumps({
                        'status': 'success',
                        'message': f'Webhook {webhook.name} is active and ready to receive data'
                    }),
                    status=200,
                    headers=[('Content-Type', 'application/json')]
                )
            
            # Get webhook data - for type='http', we need to parse JSON manually
            webhook_data = {}
            try:
                body = request.httprequest.get_data(as_text=True)
                _logger.info(f'Received raw webhook data: {body[:500] if body else "No body"}')
                if body:
                    webhook_data = json.loads(body)
                    _logger.info(f'Successfully parsed JSON data: {list(webhook_data.keys()) if isinstance(webhook_data, dict) else type(webhook_data)}')
                else:
                    _logger.warning('No request body received')
            except json.JSONDecodeError as e:
                _logger.error(f'Error parsing webhook data as JSON: {e}')
                return request.make_response('Invalid JSON data', status=400)
            except Exception as e:
                _logger.error(f'Unexpected error parsing webhook data: {e}')
                return request.make_response(f'Error parsing request: {str(e)}', status=400)
            
            _logger.info(f'Received webhook for {webhook.name}, data type: {type(webhook_data)}')
            
            # Process webhook data with sudo to bypass access rights
            result = webhook.sudo().process_webhook_data(webhook_data)
            
            return request.make_response(
                json.dumps({
                    'status': 'success',
                    'message': f'Order processed successfully: {result.name if result else "No order created"}'
                }),
                status=200,
                headers=[('Content-Type', 'application/json')]
            )
            
        except Exception as e:
            _logger.error(f'Error processing webhook {webhook_id}: {str(e)}')
            return request.make_response(
                json.dumps({'status': 'error', 'message': str(e)}),
                status=500,
                headers=[('Content-Type', 'application/json')]
            )
    
    def _verify_webhook_signature(self, request, secret):
        """Verify webhook signature"""
        signature = request.headers.get('X-WC-Webhook-Signature')
        if not signature:
            return False
        
        # Get request body
        body = request.get_data()
        
        # Calculate expected signature
        expected_signature = hmac.new(
            secret.encode('utf-8'),
            body,
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures
        return hmac.compare_digest(signature, expected_signature)
    
    @http.route('/woocommerce/webhook/test/<int:webhook_id>', type='http', auth='public', methods=['GET'], csrf=False)
    def webhook_test(self, webhook_id, **kwargs):
        """Test webhook endpoint"""
        try:
            webhook = request.env['woocommerce.order.webhook'].browse(webhook_id)
            if not webhook.exists():
                return request.make_response('Webhook not found', status=404)
            
            return request.make_response(
                f'Webhook {webhook.name} is active and ready to receive data',
                status=200
            )
            
        except Exception as e:
            _logger.error(f'Error testing webhook {webhook_id}: {str(e)}')
            return request.make_response('Error testing webhook', status=500)
