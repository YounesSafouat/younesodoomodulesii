from odoo import models, fields, api, _
from odoo.exceptions import UserError, MissingError
import base64
from PyPDF2 import PdfWriter, PdfReader
import io
import logging
from bs4 import BeautifulSoup
import re

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    sign_request_id = fields.Many2one(
        'sign.request',
        string='Signature Request',
        readonly=True,
        help="Related signature request for this sale order"
    )
    
    sign_request_state = fields.Selection(
        related='sign_request_id.state',
        string='Signature Status',
        readonly=True,
        help="Status of the signature request"
    )
    
    sale_representative_id = fields.Many2one(
        'res.partner',
        string='Sale Representative',
        help="Sale representative for this sale order"
    )
    
    signed_by = fields.Char(
        string='Signed By',
        readonly=True,
        compute='_compute_signed_by',
    )
    
    signed_on = fields.Datetime(
        string='Signed On',
        readonly=True,
        compute='_compute_signed_on',
    )
    
    signature = fields.Binary(
        string='Signature',
        readonly=True,
        compute='_compute_signature',
    )
    
    sum_kwh = fields.Float(
        string='Sum KWh',
        readonly=True,
        compute='_compute_sum_kwh',
    )
    amount_without_prime = fields.Monetary(
        string='Amount without Prime',compute='_compute_amount_without_prime', store=True
    )
    amount_ttc_without_prime = fields.Monetary(
        string='Amount without Prime',compute='_compute_amount_without_prime', store=True
    )
    new_tax_totals = fields.Binary(
        string="Invoice Totals",
        compute='_compute_tax_new_totals',
        help='Edit Tax amounts if you encounter rounding issues.',
        exportable=False,
    )
    email_sent = fields.Many2one('mail.mail', string='Email Sent', readonly=True, help="Sent email for this sale order" )
    email_state = fields.Selection([
        ('outgoing', 'Sortant'),
        ('sent', 'Envoyé'),
        ('received', 'Reçu'),
        ('exception', "Échec de l'envoi"),
        ('cancel', 'Annulé'),
    ], string="État de l'email", default='outgoing', related='email_sent.state')
    sign_template_id = fields.Many2one('sign.template', string="Signature Template", readonly=True)


    def email_mark_outgoing(self):
        self.email_sent.mark_outgoing()


    @api.depends_context('lang')
    @api.depends('order_line.price_subtotal', 'currency_id', 'company_id', 'payment_term_id')
    def _compute_tax_new_totals(self):
        AccountTax = self.env['account.tax']
        for order in self:
            order_lines = order.order_line.filtered(lambda x: not x.display_type and (not x.product_id or not x.product_id.prime_product))
            base_lines = [line._prepare_base_line_for_taxes_computation() for line in order_lines]
            base_lines += order._add_base_lines_for_early_payment_discount()
            AccountTax._add_tax_details_in_base_lines(base_lines, order.company_id)
            AccountTax._round_base_lines_tax_details(base_lines, order.company_id)
            order.new_tax_totals = AccountTax._get_tax_totals_summary(
                base_lines=base_lines,
                currency=order.currency_id or order.company_id.currency_id,
                company=order.company_id,
            )
            order.new_tax_totals['amount_without_prime'] = order.amount_without_prime
            order.new_tax_totals['amount_ttc_without_prime'] = order.amount_ttc_without_prime

    @api.depends('order_line.price_subtotal', 'currency_id', 'company_id', 'payment_term_id')
    def _compute_tax_totals(self):
        res = super()._compute_tax_totals()
        for order in self:

            order.tax_totals['amount_without_prime'] = order.amount_without_prime
            order.tax_totals['amount_ttc_without_prime'] = order.amount_ttc_without_prime


    @api.depends('order_line', 'order_line.price_total',  'order_line.price_subtotal',
                 'order_line.product_id.prime_product')
    def _compute_amount_without_prime(self):
        for order in self:
            amount_ht = 0.0
            amount_ttc = 0.0
            for line in order.order_line:
                if line.product_id and not line.product_id.prime_product:
                    amount_ht += line.price_subtotal
                    amount_ttc += line.price_total
            order.amount_without_prime = amount_ht
            order.amount_ttc_without_prime = amount_ttc


    def action_send_sale_signature_request(self):
        """Send the signature request for the sale order."""
        if not self.sign_template_id:
            sale_order_pdf_data = self._generate_fallback_pdf()

            self._create_signature_request(sale_order_pdf_data)

        customer_role = self.env.ref('sign.sign_item_role_customer', raise_if_not_found=False)

        wizard = self.env['sign.send.request'].create({
            'template_id': self.sign_template_id.id,
            'subject': _('Signature Request - %s') % self.name,
            'filename': ('%s - Signature Request') % self.name,
            'reference_doc': f"sale.order,{self.id}",
            'signer_id': self.partner_id.id,
        })
        
        sign_item_role_user = self.env.ref('sign.sign_item_role_user', raise_if_not_found=False)

        signers = self.env['sign.send.request.signer'].create([{'partner_id': self.partner_id.id,
                                                                'role_id': customer_role.id, 'sign_send_request_id':wizard.id},
                                                               {'partner_id': self.user_id.partner_id.id,
                                                                'role_id': sign_item_role_user.id,
                                                                'sign_send_request_id': wizard.id}
                                                               ])

        wizard.with_context(default_signer_id=self.partner_id.id)._onchange_template_id()
        return {
            'name': "Send request to sign",
            'type': 'ir.actions.act_window',
            'res_model': 'sign.send.request',
            'target': 'new',
            'res_id': wizard.id,
            'views': [[False, 'form']],
        }


    @api.model
    def write(self, values):
        result = super().write(values)
        if 'state' in values:
            # Find related CRM leads and update their stages
            self._update_related_crm_leads()
        return result

    def _update_related_crm_leads(self):
        """Update CRM lead stages based on sale order state"""
        for order in self:
            # Find leads that have this order as their last order
            leads = self.env['crm.lead'].search([
                ('order_ids', 'in', order.id)
            ])
            
            for lead in leads:
                # Recompute to ensure we have the latest last_order
                lead._compute_last_order()
                # Only update if this is indeed the last order
                if lead.last_order and lead.last_order.id == order.id:
                    lead._sync_stage_with_order_state()

    def _compute_sum_kwh(self):
        for rec in self:
            rec.sum_kwh = sum(line.product_uom_qty * line.product_id.kwh for line in rec.order_line)
    
    def _compute_signed_by(self):
        for rec in self:
            if rec.sign_request_id and rec.sign_request_id.request_item_ids:
                rec.signed_by = rec.sign_request_id.request_item_ids[0].partner_id.name
            else:
                rec.signed_by = False

    def _compute_signed_on(self):
        for rec in self:
            if rec.sign_request_id and rec.sign_request_id.request_item_ids:
                rec.signed_on = rec.sign_request_id.request_item_ids[0].signing_date
            else:
                rec.signed_on = False

    def _compute_signature(self):
        for rec in self:
            if rec.sign_request_id and rec.sign_request_id.request_item_ids:
                rec.signature = rec.sign_request_id.request_item_ids[0].signature
            else:
                rec.signature = False


    def _generate_fallback_pdf(self):
        """Generate a fallback PDF for the sale order using available reports."""
        report = None
        tried_report_ids = set()

        try:
            # pdf_data = report._render_qweb_pdf(self.id)[0]
            pdf_data, _report_type = self.env['ir.actions.report']._render_qweb_pdf(
                'sale.action_report_saleorder',
                res_ids=self.id,
            )
            self.env['ir.attachment'].create({
                'name': f"SaleOrder_{self.name}.pdf",
                'type': 'binary',
                'datas': base64.b64encode(pdf_data),
                'mimetype': 'application/pdf',
                'res_model': 'sale.order',
                'res_id': self.id,
            })
            return pdf_data
        except MissingError as e:
            _logger.error(f"MissingError rendering PDF for sale order {self.name}: {str(e)}")

        except Exception as e:
            _logger.error(f"Error rendering PDF for sale order {self.name}: {str(e)}")
            raise UserError(_("Failed to generate sale order PDF. Please check the report configuration."))

    def _create_signature_request(self, sale_order_pdf_data=None):
        self.ensure_one()
        if not (self.sale_representative_id and self.sale_representative_id.sign_template_id):
            raise UserError(_("Please assign a sale representative with a signature template."))
        
        signature_template = self.sale_representative_id.sign_template_id
        if not signature_template.attachment_id:
            raise UserError(_("The selected signature template has no attachment."))

        combined_pdf_data, sale_order_page_count = self._create_combined_pdf_data(
            sale_order_pdf_data, return_sale_order_page_count=True
        )

        if not self.partner_id.email:
            raise UserError(_("Customer email is required for signature request."))

        combined_attachment = None
        temp_template = None
        try:
            combined_attachment = self.env['ir.attachment'].create({
                'name': f"Combined_SO_Template_{self.name}.pdf",
                'type': 'binary',
                'datas': base64.b64encode(combined_pdf_data),
                'mimetype': 'application/pdf',
                'res_model': 'sale.order',
                'res_id': self.id,
            })

            temp_template = self.env['sign.template'].create({
                'name': f"Devis:  {self.name}",
                'attachment_id': combined_attachment.id,
            })

            for item in signature_template.sign_item_ids:
                self.env['sign.item'].create({
                    'template_id': temp_template.id,
                    'page': item.page + sale_order_page_count,
                    'posX': item.posX,
                    'posY': item.posY,
                    'width': item.width,
                    'height': item.height,
                    'required': item.required,
                    'type_id': item.type_id.id,
                    'responsible_id': item.responsible_id.id,
                })

            role_ids = set()
            for item in temp_template.sign_item_ids:
                if item.responsible_id:
                    role_ids.add(item.responsible_id.id)
            # if not role_ids:
            #     raise UserError(_("No responsible user found in the signature template."))

            request_items = []
            for role_id in role_ids:
                request_items.append((0, 0, {
                    'partner_id': self.partner_id.id,
                    'role_id': role_id,
                }))

            self.sign_template_id = temp_template

        except Exception as e:
            _logger.error(f"Error creating signature request for {self.name}: {str(e)}")
            if combined_attachment and combined_attachment.exists():
                try:
                    combined_attachment.unlink()
                except Exception as cleanup_e:
                    _logger.warning(f"Failed to cleanup combined_attachment: {cleanup_e}")
            if temp_template and temp_template.exists():
                try:
                    temp_template.unlink()
                except Exception as cleanup_e:
                    _logger.warning(f"Failed to cleanup temp_template: {cleanup_e}")
            raise

    @api.model_create_multi
    def create(self, vals):
        records = super().create(vals)
        for rec in records:
            if rec.partner_id and not rec.sale_representative_id and rec.partner_id.user_id:
                rec.sign_request = rec._create_signature_request_for_order(rec)
        return records

    def _create_combined_pdf_data(self, sale_order_pdf_data=None, return_sale_order_page_count=False):

        template_attachment = self.sale_representative_id.sign_template_id.attachment_id
        try:
            _logger.info(f"Creating combined PDF for sale order {self.name}")
            pdf_writer = PdfWriter()
            sale_order_page_count = 0

            try:
                sale_order_pdf_reader = PdfReader(io.BytesIO(sale_order_pdf_data))
                for page in sale_order_pdf_reader.pages:
                    pdf_writer.add_page(page)
                sale_order_page_count = len(sale_order_pdf_reader.pages)
                _logger.info(f"Successfully added sale order PDF with {sale_order_page_count} pages")
            except Exception as e:
                _logger.error(f"Error reading sale order PDF: {str(e)}")
                raise UserError(_("Invalid sale order PDF data."))

            try:
                template_pdf_data = base64.b64decode(template_attachment.datas)
                template_pdf = PdfReader(io.BytesIO(template_pdf_data))
                for page in template_pdf.pages:
                    pdf_writer.add_page(page)
                _logger.info(f"Successfully added template PDF with {len(template_pdf.pages)} pages")
            except Exception as e:
                _logger.error(f"Error reading template PDF: {str(e)}")
                raise UserError(_("Invalid template PDF data."))

            combined_pdf_buffer = io.BytesIO()
            pdf_writer.write(combined_pdf_buffer)
            combined_pdf_data = combined_pdf_buffer.getvalue()
            combined_pdf_buffer.close()

            _logger.info(f"Successfully created combined PDF with {len(pdf_writer.pages)} total pages")
            if return_sale_order_page_count:
                return combined_pdf_data, sale_order_page_count
            return combined_pdf_data

        except Exception as e:
            _logger.error(f"Error creating combined PDF for {self.name}: {str(e)}")
            raise UserError(_("Failed to create combined PDF."))

    def _get_order_lines_to_report(self):
        lines = super()._get_order_lines_to_report()
        if lines:
            lines = lines.filtered(lambda line: not line.product_id.prime_product)
        return lines



class SignRequestItem(models.Model):
    _name = "sign.request.item"
    _inherit = ['sign.request.item']

    def _sign(self, signature, **kwargs):
        """Give view access to the signer on the completed documents."""
        super()._sign(signature, **kwargs)
        if self.sign_request_id.state == 'signed':
            sale_order = self.env['sale.order'].search([('sign_request_id', '=', self.sign_request_id.id)])
            if sale_order:
                sale_order.action_confirm()
                sale_order.require_signature = True
                attachment = None
                if self.sign_request_id.completed_document:
                    attachment = self.env['ir.attachment'].create({
                        'name': f"{sale_order.name}_signed.pdf",
                        'datas': self.sign_request_id.completed_document,
                        'res_model': 'sale.order',
                        'res_id': sale_order.id,
                        'type': 'binary',
                        'mimetype': 'application/pdf',
                    })
                sale_order.message_post(
                    body=f"Sale order {sale_order.name} confirmed by {self.partner_id.name} on {fields.Datetime.now()} ",
                    attachment_ids=[attachment.id] if attachment else []
                )

