from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
from PyPDF2 import PdfWriter, PdfReader
import io
import logging

_logger = logging.getLogger(__name__)

class ResPartner(models.Model):
    _inherit = 'res.partner'

    sign_template_id = fields.Many2one(
        'sign.template',
        string='Signature Template', ondelete="restrict"
    )
    is_representative = fields.Boolean(
        string='Is Representative',
        default=False,
    )
    
    condition_terms = fields.Text(
        string='Condition Terms',
    )