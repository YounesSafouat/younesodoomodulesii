# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.http import request


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    
    stripe_api_key = fields.Char(
        string='Stripe API Key',
        config_parameter='stripe_integration.api_key',
        help='Your Stripe Secret API Key (starts with sk_test_ or sk_live_)'
    )
    
    stripe_webhook_url = fields.Char(
        string='Webhook URL',
        readonly=True,
        compute='_compute_webhook_url',
        store=False,
        help='Use this URL when configuring webhooks in Stripe Dashboard'
    )
    
    def _get_webhook_url(self):
        """Helper method to get webhook URL"""
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        if not base_url:
            try:
                if hasattr(request, 'httprequest') and request.httprequest:
                    base_url = request.httprequest.host_url.rstrip('/')
            except:
                pass
        
        return f"{base_url}/stripe/webhook" if base_url else "/stripe/webhook"
    
    @api.model
    def get_default_stripe_webhook_url(self):
        """Get default webhook URL for settings form"""
        return self._get_webhook_url()
    
    @api.model
    def default_get(self, fields_list):
        """Override to ensure webhook URL is computed on form load"""
        res = super().default_get(fields_list)
        if 'stripe_webhook_url' in fields_list:
            res['stripe_webhook_url'] = self._get_webhook_url()
        return res
    
    @api.depends()
    def _compute_webhook_url(self):
        """Compute the webhook URL for display"""
        webhook_url = self._get_webhook_url()
        for record in self:
            record.stripe_webhook_url = webhook_url