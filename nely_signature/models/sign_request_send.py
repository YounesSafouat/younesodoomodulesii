from odoo import api, fields, models

class SignRequestSend(models.TransientModel):
    _inherit = 'sign.send.request'

    def send_request(self):
        res = super().send_request()
        for request in self:
            if request.reference_doc and request.reference_doc.split(',')[0] == 'sale.order':
                sale = self.env['sale.order'].browse(int(request.reference_doc.split(',')[1]))
                if sale and sale.require_signature:
                    sale.write({'state': 'sent'})
                return {'type': 'ir.actions.act_window_close'}

        return res

    def create_request(self):
        res = super().create_request()

        if res and res.reference_doc and res.reference_doc._name and res.reference_doc._name == 'sale.order':
            res.reference_doc.write({'sign_request_id': res.id})
        return res