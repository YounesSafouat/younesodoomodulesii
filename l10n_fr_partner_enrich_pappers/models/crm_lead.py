from odoo import models, fields, api, _
from odoo.exceptions import UserError, MissingError

import base64
import logging

_logger = logging.getLogger(__name__)

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    
    
    @api.onchange('street')
    def _onchange_street(self):
        if not self.street:
            return

        try:
            geolocator = Nominatim(user_agent="odoo_autofill")
            location = geolocator.geocode(self.street)
            if location and location.raw.get("display_name"):
                addr = location.raw.get("address", {})

                self.city = addr.get("city") or addr.get("town") or addr.get("village")
                self.zip = addr.get("postcode")
                if addr.get("country"):
                    country = self.env['res.country'].search(
                        [('name', 'ilike', addr.get("country"))], limit=1
                    )
                    if country:
                        self.country_id = country.id
                if addr.get("state"):
                    state = self.env['res.country.state'].search(
                        [('name', 'ilike', addr.get("state"))], limit=1
                    )
                    if state:
                        self.state_id = state.id
        except Exception:
            pass
    def get_company_docs(self):
        pappers_document = self.env['ir.config_parameter'].sudo().get_param(
            'l10n_fr_partner_enrich_pappers.pappers_document', False
        )
        if not pappers_document:
            _logger.info("Company is not configured to get Pappers documents.")
            return False
        if self.partner_id:
            pdf_data = self.partner_id.get_company_docs()
            if pdf_data and isinstance(pdf_data, bytes):
                # Create the attachment
                attachment = self.env['ir.attachment'].create({
                    'name': f'Extrait_Pappers_{self.partner_id.siren_pappers or self.partner_id.name}.pdf',
                    'type': 'binary',
                    'datas': base64.b64encode(pdf_data),
                    'mimetype': 'application/pdf',
                    'res_model': 'crm.lead',
                    'res_id': self.id,
                })
                _logger.info(f"Attached Pappers document to lead {self.name} (ID: {self.id})")
                self.message_post(
                    body=_("Pappers Extrait PDF attached."),
                    attachment_ids=[attachment.id],
                    message_type='notification',
                    subtype_xmlid='mail.mt_note',
                )
    def html_to_text(self, html_content):
        """Convert HTML content to plain text"""
        import re
        from bs4 import BeautifulSoup
        
        if not html_content:
            return ""
        
        try:
            # Parse HTML content
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Get text content
            text = soup.get_text()
            
            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            # Remove extra spaces and normalize
            text = re.sub(r'\s+', ' ', text)
            
            return text.strip()
            
        except Exception as e:
            _logger.warning(f"Error converting HTML to text: {str(e)}")
            # Fallback: simple regex-based HTML tag removal
            import re
            clean = re.compile('<.*?>')
            return re.sub(clean, '', html_content)