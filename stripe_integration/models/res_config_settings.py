# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


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
        help='Use this URL when configuring webhooks in Stripe Dashboard'
    )
    
    @api.depends()
    def _compute_webhook_url(self):
        """Compute the webhook URL for display"""
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            record.stripe_webhook_url = f"{base_url}/stripe/webhook"