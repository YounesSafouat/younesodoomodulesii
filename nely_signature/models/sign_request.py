from odoo import models, fields, api, _

class SignRequest(models.Model):
    _inherit = 'sign.request'

    def _message_send_mail(self, body, email_layout_xmlid, message_values, notif_values, mail_values, force_send=False, **kwargs):
        res = super()._message_send_mail(body, email_layout_xmlid, message_values, notif_values, mail_values, force_send=True, **kwargs)
        if self.env.context.get('active_model') == 'sale.order':
            sale_order = self.env['sale.order'].browse(self.env.context.get('active_id'))
            sale_order.write({'email_sent': res})
        # res.send()
        return res

   