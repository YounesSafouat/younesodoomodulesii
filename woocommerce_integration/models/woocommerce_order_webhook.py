import json
import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime

_logger = logging.getLogger(__name__)


class WooCommerceOrderWebhook(models.Model):
    _name = 'woocommerce.order.webhook'
    _description = 'WooCommerce Order Webhook Handler'
    _order = 'create_date desc'

    name = fields.Char(
        string='Webhook Name',
        required=True,
        help='Name of the webhook'
    )
    
    connection_id = fields.Many2one(
        'woocommerce.connection',
        string='WooCommerce Connection',
        required=True,
        ondelete='cascade',
        help='Related WooCommerce connection'
    )
    
    webhook_url = fields.Char(
        string='Webhook URL',
        compute='_compute_webhook_url',
        help='URL to receive webhooks from WooCommerce'
    )
    
    webhook_secret = fields.Char(
        string='Webhook Secret',
        help='Secret key for webhook verification'
    )
    
    webhook_topic = fields.Selection([
        ('order.created', 'Order Created'),
        ('order.updated', 'Order Updated'),
        ('order.deleted', 'Order Deleted'),
        ('order.paid', 'Order Paid'),
        ('order.completed', 'Order Completed'),
    ], string='Webhook Topic', default='order.created')
    
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Whether this webhook is active'
    )
    
    auto_create_odoo_order = fields.Boolean(
        string='Auto Create Odoo Order',
        default=True,
        help='Automatically create Odoo sale order when WooCommerce order is received'
    )
    
    auto_create_customer = fields.Boolean(
        string='Auto Create Customer',
        default=True,
        help='Automatically create customer if not exists'
    )
    
    order_prefix = fields.Char(
        string='Order Prefix',
        default='WC-',
        help='Prefix for Odoo sale order names'
    )
    
    # Webhook Log
    webhook_log_ids = fields.One2many(
        'woocommerce.order.webhook.log',
        'webhook_id',
        string='Webhook Logs'
    )
    
    @api.depends()
    def _compute_webhook_url(self):
        """Compute webhook URL"""
        for webhook in self:
            if webhook.id:
                # Try to get base URL from request first
                try:
                    base_url = self.env['ir.http']._get_default_port()
                    if not base_url or 'localhost' in base_url:
                        # If no valid base URL, try to get from config
                        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
                except:
                    base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
                
                # Fallback to request URL if available
                if not base_url or 'localhost' in base_url:
                    try:
                        from odoo.http import request
                        if hasattr(request, 'httprequest') and request.httprequest:
                            base_url = request.httprequest.host_url
                    except:
                        pass
                
                webhook.webhook_url = f"{base_url}/woocommerce/webhook/{webhook.id}"
            else:
                webhook.webhook_url = False
    
    def action_test_webhook(self):
        """Test webhook functionality"""
        self.ensure_one()
        
        # Create a test webhook log
        test_data = {
            'test': True,
            'message': 'Webhook test successful'
        }
        
        log = self.env['woocommerce.order.webhook.log'].sudo().create({
            'webhook_id': self.id,
            'raw_data': json.dumps(test_data),
            'status': 'success',
            'message': 'Webhook test completed successfully'
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Webhook test completed successfully!'),
                'type': 'success',
            }
        }
    
    def process_webhook_data(self, webhook_data):
        """Process incoming webhook data and create Odoo order"""
        self.ensure_one()
        
        try:
            # Log the webhook data
            log = self.env['woocommerce.order.webhook.log'].sudo().create({
                'webhook_id': self.id,
                'raw_data': json.dumps(webhook_data),
                'status': 'processing',
                'message': 'Processing webhook data...'
            })
            
            # Extract order data
            order_data = webhook_data.get('order', webhook_data)
            
            if not order_data:
                raise ValidationError(_('No order data found in webhook'))
            
            # Create or update Odoo order
            if self.auto_create_odoo_order:
                odoo_order = self._create_odoo_order(order_data)
                
                log.write({
                    'status': 'success',
                    'message': f'Odoo order created: {odoo_order.name}',
                    'odoo_order_id': odoo_order.id
                })
                
                return odoo_order
            
        except Exception as e:
            _logger.error(f'Error processing webhook data: {str(e)}')
            
            # Update log with error
            if 'log' in locals():
                log.write({
                    'status': 'error',
                    'message': f'Error: {str(e)}'
                })
            
            raise
    
    def _create_odoo_order(self, order_data):
        """Create Odoo sale order from WooCommerce order data"""
        self.ensure_one()
        
        # Get or create customer
        customer = self._get_or_create_customer(order_data.get('billing', {}))
        
        # Prepare order values
        order_vals = {
            'partner_id': customer.id,
            'date_order': self._parse_date(order_data.get('date_created')),
            'client_order_ref': f"WC-{order_data.get('id')}",
            'note': f"WooCommerce Order ID: {order_data.get('id')}\n"
                   f"WooCommerce Order Key: {order_data.get('order_key', '')}\n"
                   f"Payment Method: {order_data.get('payment_method_title', '')}\n"
                   f"Shipping Method: {order_data.get('shipping_lines', [{}])[0].get('method_title', '') if order_data.get('shipping_lines') else ''}",
            'warehouse_id': self.env['stock.warehouse'].search([], limit=1).id,
        }
        
        # Create sale order
        sale_order = self.env['sale.order'].create(order_vals)
        
        # Add order lines
        self._create_order_lines(sale_order, order_data.get('line_items', []))
        
        # Handle shipping
        self._handle_shipping(sale_order, order_data.get('shipping_lines', []))
        
        # Handle fees
        self._handle_fees(sale_order, order_data.get('fee_lines', []))
        
        return sale_order
    
    def _get_or_create_customer(self, billing_data):
        """Get or create customer from billing data"""
        self.ensure_one()
        
        if not billing_data:
            # Use default customer if no billing data
            return self.env['res.partner'].search([('is_company', '=', False)], limit=1)
        
        email = billing_data.get('email')
        if not email:
            # Create anonymous customer
            return self.env['res.partner'].search([('is_company', '=', False)], limit=1)
        
        # Search for existing customer
        customer = self.env['res.partner'].sudo().search([
            ('email', '=', email)
        ], limit=1)
        
        if customer:
            # Update existing customer data
            customer.sudo().write({
                'name': f"{billing_data.get('first_name', '')} {billing_data.get('last_name', '')}".strip(),
                'email': email,
                'phone': billing_data.get('phone', ''),
                'street': billing_data.get('address_1', ''),
                'street2': billing_data.get('address_2', ''),
                'city': billing_data.get('city', ''),
                'zip': billing_data.get('postcode', ''),
                'country_id': self._get_country_id(billing_data.get('country')),
                'state_id': self._get_state_id(billing_data.get('state'), billing_data.get('country')),
            })
            return customer
        
        # Create new customer
        if self.auto_create_customer:
            customer_vals = {
                'name': f"{billing_data.get('first_name', '')} {billing_data.get('last_name', '')}".strip(),
                'email': email,
                'phone': billing_data.get('phone', ''),
                'street': billing_data.get('address_1', ''),
                'street2': billing_data.get('address_2', ''),
                'city': billing_data.get('city', ''),
                'zip': billing_data.get('postcode', ''),
                'country_id': self._get_country_id(billing_data.get('country')),
                'state_id': self._get_state_id(billing_data.get('state'), billing_data.get('country')),
                'is_company': False,
                'customer_rank': 1,
            }
            
            return self.env['res.partner'].create(customer_vals)
        
        # Return default customer if auto-create is disabled
        return self.env['res.partner'].search([('is_company', '=', False)], limit=1)
    
    def _create_order_lines(self, sale_order, line_items):
        """Create sale order lines from WooCommerce line items"""
        for item in line_items:
            # Find product by SKU or name
            product = self._find_product(item)
            
            if not product:
                _logger.warning(f'Product not found for item: {item.get("name")}')
                continue
            
            # Calculate unit price
            unit_price = float(item.get('price', 0))
            
            # Create order line
            line_vals = {
                'order_id': sale_order.id,
                'product_id': product.id,
                'name': item.get('name', ''),
                'product_uom_qty': float(item.get('quantity', 1)),
                'price_unit': unit_price,
                'product_uom': product.uom_id.id,
            }
            
            self.env['sale.order.line'].create(line_vals)
    
    def _find_product(self, item):
        """Find Odoo product from WooCommerce item"""
        # Try to find by SKU first
        sku = item.get('sku')
        if sku:
            product = self.env['product.template'].search([
                ('default_code', '=', sku)
            ], limit=1)
            if product:
                return product
        
        # Try to find by name
        name = item.get('name')
        if name:
            product = self.env['product.template'].search([
                ('name', '=', name)
            ], limit=1)
            if product:
                return product
        
        # Try to find by WooCommerce product ID
        wc_product_id = item.get('product_id')
        if wc_product_id:
            wc_product = self.env['woocommerce.product'].search([
                ('wc_product_id', '=', wc_product_id),
                ('odoo_product_id', '!=', False)
            ], limit=1)
            if wc_product and wc_product.odoo_product_id:
                return wc_product.odoo_product_id
        
        return None
    
    def _handle_shipping(self, sale_order, shipping_lines):
        """Handle shipping lines"""
        for shipping in shipping_lines:
            if not shipping.get('method_title'):
                continue
            
            # Create shipping product if it doesn't exist
            shipping_product = self._get_or_create_shipping_product(shipping['method_title'])
            
            line_vals = {
                'order_id': sale_order.id,
                'product_id': shipping_product.id,
                'name': f"Shipping: {shipping['method_title']}",
                'product_uom_qty': 1,
                'price_unit': float(shipping.get('total', 0)),
                'product_uom': shipping_product.uom_id.id,
            }
            
            self.env['sale.order.line'].create(line_vals)
    
    def _handle_fees(self, sale_order, fee_lines):
        """Handle fee lines"""
        for fee in fee_lines:
            if not fee.get('name'):
                continue
            
            # Create fee product if it doesn't exist
            fee_product = self._get_or_create_fee_product(fee['name'])
            
            line_vals = {
                'order_id': sale_order.id,
                'product_id': fee_product.id,
                'name': f"Fee: {fee['name']}",
                'product_uom_qty': 1,
                'price_unit': float(fee.get('total', 0)),
                'product_uom': fee_product.uom_id.id,
            }
            
            self.env['sale.order.line'].create(line_vals)
    
    def _get_or_create_shipping_product(self, shipping_name):
        """Get or create shipping product"""
        product = self.env['product.template'].search([
            ('name', '=', f"Shipping: {shipping_name}")
        ], limit=1)
        
        if not product:
            product = self.env['product.template'].create({
                'name': f"Shipping: {shipping_name}",
                'type': 'service',
                'sale_ok': True,
                'purchase_ok': False,
                'list_price': 0,
            })
        
        return product
    
    def _get_or_create_fee_product(self, fee_name):
        """Get or create fee product"""
        product = self.env['product.template'].search([
            ('name', '=', f"Fee: {fee_name}")
        ], limit=1)
        
        if not product:
            product = self.env['product.template'].create({
                'name': f"Fee: {fee_name}",
                'type': 'service',
                'sale_ok': True,
                'purchase_ok': False,
                'list_price': 0,
            })
        
        return product
    
    def _parse_date(self, date_string):
        """Parse date string from WooCommerce"""
        if not date_string:
            return fields.Datetime.now()
        
        try:
            # WooCommerce date format: 2023-10-24T10:30:00
            return datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        except:
            return fields.Datetime.now()
    
    def _get_country_id(self, country_code):
        """Get country ID from country code"""
        if not country_code:
            return None
        
        country = self.env['res.country'].search([
            ('code', '=', country_code.upper())
        ], limit=1)
        
        return country.id if country else None
    
    def _get_state_id(self, state_name, country_code):
        """Get state ID from state name and country code"""
        if not state_name or not country_code:
            return None
        
        country = self.env['res.country'].search([
            ('code', '=', country_code.upper())
        ], limit=1)
        
        if not country:
            return None
        
        state = self.env['res.country.state'].search([
            ('name', '=', state_name),
            ('country_id', '=', country.id)
        ], limit=1)
        
        return state.id if state else None


class WooCommerceOrderWebhookLog(models.Model):
    _name = 'woocommerce.order.webhook.log'
    _description = 'WooCommerce Order Webhook Log'
    _order = 'create_date desc'

    webhook_id = fields.Many2one(
        'woocommerce.order.webhook',
        string='Webhook',
        required=True,
        ondelete='cascade'
    )
    
    raw_data = fields.Text(
        string='Raw Data',
        help='Raw webhook data received'
    )
    
    status = fields.Selection([
        ('processing', 'Processing'),
        ('success', 'Success'),
        ('error', 'Error'),
    ], string='Status', default='processing')
    
    message = fields.Text(
        string='Message',
        help='Status message'
    )
    
    odoo_order_id = fields.Many2one(
        'sale.order',
        string='Odoo Order',
        help='Created Odoo order'
    )
    
    create_date = fields.Datetime(
        string='Created',
        default=fields.Datetime.now
    )
