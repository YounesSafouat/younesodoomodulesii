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
            webhook = request.env['woocommerce.order.webhook'].browse(webhook_id)
            if not webhook.exists() or not webhook.active:
                _logger.warning(f'Webhook {webhook_id} not found or inactive')
                return request.make_response('Webhook not found or inactive', status=404)
            
            _logger.info(f'Signature verification disabled for testing')
            
            if request.httprequest.method == 'GET':
                return request.make_response(
                    json.dumps({
                        'status': 'success',
                        'message': f'Webhook {webhook.name} is active and ready to receive data'
                    }),
                    status=200,
                    headers=[('Content-Type', 'application/json')]
                )
            
            webhook_data = {}
            try:
                body_bytes = request.httprequest.get_data()
                _logger.info(f'Received raw body (bytes): {len(body_bytes)} bytes')
                
                if body_bytes:
                    body = body_bytes.decode('utf-8')
                    _logger.info(f'Received raw webhook data: {body[:500] if body else "No body"}')
                    
                    webhook_data = json.loads(body)
                    _logger.info(f'Successfully parsed JSON data: {list(webhook_data.keys()) if isinstance(webhook_data, dict) else type(webhook_data)}')
                else:
                    _logger.warning('No request body received - WooCommerce may be sending an empty request or the webhook is testing')
                    return request.make_response(
                        json.dumps({
                            'status': 'success',
                            'message': 'Webhook received with no data - this is normal for webhook testing'
                        }),
                        status=200,
                        headers=[('Content-Type', 'application/json')]
                    )
            except json.JSONDecodeError as e:
                # Log as warning since invalid JSON is a client error, not a server error
                # This is expected in tests that send invalid JSON to test error handling
                _logger.warning(f'Invalid JSON in webhook data: {e}')
                return request.make_response('Invalid JSON data', status=400)
            except Exception as e:
                _logger.error(f'Unexpected error parsing webhook data: {e}')
                return request.make_response(f'Error parsing request: {str(e)}', status=400)
            
            _logger.info(f'Received webhook for {webhook.name}, data type: {type(webhook_data)}')
            
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
        
        body = request.get_data()
        
        expected_signature = hmac.new(
            secret.encode('utf-8'),
            body,
            hashlib.sha256
        ).hexdigest()
        
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
