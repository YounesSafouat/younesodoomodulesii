# -*- coding: utf-8 -*-

import json
import logging
import re
from odoo import api, fields, models, tools, _
from datetime import datetime
from urllib.parse import urlparse
import base64
from geopy.geocoders import Nominatim
_logger = logging.getLogger(__name__)

try:
    from stdnum.fr import siret, tva, siren
except ImportError:
    _logger.debug("Cannot import stdnum")


class ResPartner(models.Model):
    _inherit = "res.partner"

    # Base identification fields
    firstname = fields.Char("Prénom", help="Prénom du dirigeant signataire")
    lastname = fields.Char("Nom de famille", help="Nom de famille du dirigeant signataire")
    siret_pappers = fields.Char("SIRET")
    siren_pappers = fields.Char("SIREN")
    partner_gid_pappers = fields.Integer("Company database ID")
    company_registry_pappers = fields.Char("RCS Number")

    # Legal information
    legal_form_pappers = fields.Char("Legal Form")
    legal_type_pappers = fields.Selection(
        [("person", "Natural Person"), ("company", "Legal Entity")], string="Legal Type"
    )

    # Company specific fields
    capital_amount_pappers = fields.Float("Capital Amount")
    capital_currency_pappers = fields.Char("Capital Currency")
    company_creation_date_pappers = fields.Date("Creation Date")
    rcs_registration_date_pappers = fields.Date("RCS Registration Date")
    business_activity_pappers = fields.Text("Business Activity")
    workforce_size_pappers = fields.Char("Workforce Size")
    is_headquarters_pappers = fields.Boolean("Is Headquarters")

    # Additional information
    last_update_date_pappers = fields.Date("Last Update Date")

    # Pappers specific fields
    rcs_status_pappers = fields.Selection(
        [
            ("registered", "Registered"),
            ("unregistered", "Unregistered"),
            ("radiation", "Removed"),
        ],
        string="RCS Status",
    )
    company_closed_pappers = fields.Boolean("Company Closed")
    closure_date_pappers = fields.Date("Closure Date")

    
    @api.onchange('street')
    def _onchange_street_autocomplete(self):
        """Auto-populate address fields based on street input"""
        if not self.street or len(self.street.strip()) < 10:
            return
            
        try:
            # Initialize geolocator with a user agent
            geolocator = Nominatim(
                user_agent="odoo_address_autocomplete_v1.0",
                timeout=10
            )
            
            # Geocode the street address
            location = geolocator.geocode(self.street, exactly_one=True)
            
            if location and location.address:
                # Parse the address string
                address_parts = [part.strip() for part in location.address.split(',')]
                
                if len(address_parts) >= 4:
                    # Extract ZIP code (usually numeric, near the end)
                    zip_code = None
                    for part in reversed(address_parts):
                        if part.strip().replace('-', '').isdigit() and len(part.strip()) >= 5:
                            zip_code = part.strip()
                            break
                    
                    if zip_code and not self.zip:
                        self.zip = zip_code
                    
                    # Extract country (usually last part)
                    country_name = address_parts[-1].strip()
                    if country_name and not self.country_id:
                        country_record = self.env['res.country'].search([
                            '|', ('name', 'ilike', country_name), ('code', 'ilike', country_name)
                        ], limit=1)
                        if country_record:
                            self.country_id = country_record.id
                    
                    # Extract state (usually second to last, before country)
                    if len(address_parts) >= 2:
                        state_name = address_parts[-2].strip()
                        # Remove ZIP code from state if it's there
                        if zip_code and zip_code in state_name:
                            state_name = state_name.replace(zip_code, '').strip().rstrip(',').strip()
                        
                        if state_name and not self.state_id:
                            state_record = self.env['res.country.state'].search([
                                ('name', 'ilike', state_name)
                            ], limit=1)
                            if state_record:
                                self.state_id = state_record.id
                    
                    # Extract city (usually third from last, or look for county patterns)
                    if len(address_parts) >= 3:
                        # Look for city (avoid county names)
                        for i in range(len(address_parts) - 3, -1, -1):
                            potential_city = address_parts[i].strip()
                            # Skip if it looks like a county
                            if not potential_city.lower().endswith('county') and potential_city:
                                if not self.city:
                                    self.city = potential_city
                                break
                
                _logger.info(f"Address autocomplete successful for: {self.street}")
                
        except GeocoderTimedOut:
            _logger.warning("Geocoder timed out while processing address")
        except GeocoderServiceError as e:
            _logger.warning(f"Geocoder service error: {str(e)}")
        except Exception as e:
            _logger.error(f"Unexpected error in address autocomplete: {str(e)}")




    def get_company_data(self):
        """Get company data from Pappers API"""
        pappers_api = self.env["pappers.api"]
        company_data = pappers_api.get_company_details(self.siren_pappers)
        return company_data
    def get_company_docs(self):
        """Get company documents from Pappers API (expects a PDF in result)"""
        pappers_document = self.env['ir.config_parameter'].sudo().get_param(
            'l10n_fr_partner_enrich_pappers.pappers_document', False
        )
        if not pappers_document:
            _logger.info("Company is not configured to get Pappers documents.")
            return False
        pappers_api = self.env["pappers.api"]
        # We expect the API to return a PDF (bytes) directly
        pdf_data = pappers_api.search_extraits(self.siren_pappers)
        print("================================================")
        print(pdf_data)
        print("================================================")
        if pdf_data and isinstance(pdf_data, bytes):
            try:
                # Create the attachment
                attachment = self.env['ir.attachment'].create({
                    'name': f'Extrait_Pappers_{self.siren_pappers or self.name}.pdf',
                    'type': 'binary',
                    'datas': base64.b64encode(pdf_data),
                    'mimetype': 'application/pdf',
                    'res_model': self._name,
                    'res_id': self.id,
                })
                # Post a message in the chatter (notes) with the attachment
                self.message_post(
                    body=_("Pappers Extrait PDF attached."),
                    attachment_ids=[attachment.id],
                    message_type='notification',
                    subtype_xmlid='mail.mt_note',
                )
                _logger.info(f"Attached Pappers PDF document to partner {self.name}")
            except Exception as e:
                _logger.error(f"Failed to attach Pappers PDF document: {e}")
        else:
            _logger.warning(f"No PDF data received from Pappers for partner {self.name}")
        return pdf_data
    def _extract_domain_from_website(self, website):
        """Extract domain from website URL"""
        if not website:
            return False
        try:
            parsed = urlparse(website if '://' in website else f'http://{website}')
            return parsed.netloc or parsed.path
        except Exception:
            return False

    def _get_value_from_dict(self, data_dict, field_path):
        """Extract value from nested dictionary using dot notation path"""
        if not field_path:
            return False
        current = data_dict
        for key in field_path.split('.'):
            if not isinstance(current, dict):
                return False
            current = current.get(key, {})
        return current if current != {} else False

    def _convert_value_for_field(self, value, field_name):
        """Convert API value to appropriate Odoo field type"""
        if not value or not field_name:
            return False

        field = self._fields.get(field_name)
        if not field:
            _logger.warning(f"Field {field_name} does not exist in res.partner model")
            return False

        try:
            if field.type == 'date' and isinstance(value, str):
                return datetime.strptime(value, "%Y-%m-%d").date()
            elif field.type == 'float' and (isinstance(value, str) or isinstance(value, int)):
                return float(value)
            elif field.type == 'integer' and (isinstance(value, str) or isinstance(value, float)):
                return int(value)
            elif field.type == 'boolean' and isinstance(value, str):
                return value.lower() in ['true', '1', 'yes']
            return value
        except (ValueError, TypeError) as e:
            _logger.warning(f"Error converting value '{value}' for field '{field_name}': {str(e)}")
            return False

    def format_data_company(self, pappers_data):
        """Format Pappers data according to field mappings"""
        if not pappers_data:
            return {}

        # Get active field mappings
        mappings = self.env['pappers.field.mapping'].search([
            ('active', '=', True),
            ('company_id', 'in', [False, self.env.company.id])
        ])

        if not mappings:
            return {}

        formatted_data = {
            'country_id': self.env.ref('base.fr').id,
            'lang': 'fr_FR',  # Add France as default country
        }
        
        for mapping in mappings:
            # Retrieve the value from the nested dictionary using dot notation
            pappers_value = self._get_value_from_dict(pappers_data, mapping.pappers_field)

            if pappers_value:
                # Convert the value to the appropriate Odoo field type
                converted_value = self._convert_value_for_field(pappers_value, mapping.odoo_field)
                if converted_value is not False:
                    formatted_data[mapping.odoo_field] = converted_value

        return formatted_data

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        """Override to inject pappers visibility context"""
        res = super().get_view(view_id, view_type, **options)
        
        if view_type == 'form':
            hide_tab = self.env['ir.config_parameter'].sudo().get_param(
                'l10n_fr_partner_enrich_pappers.hide_tab', 'False'
            ).lower() == 'true'
            
            if hide_tab:
                if not res.get('context'):
                    res['context'] = {}
                res['context'].update({
                    'hide_pappers_tab': hide_tab,
                })
        
        return res

    def _extract_identifier_from_name(self, name):
        """Extract SIRET, SIREN or VAT number from partner name if present"""
        if not name:
            return None, None

        # Clean the name by removing spaces and converting to uppercase
        clean_name = name.replace(" ", "").upper()
        _logger.info(f"Cleaned name: {clean_name}")
        
        # First try to find a SIRET (14 digits)
        try:
            potential_siret = re.search(r"\d{14}", clean_name)
            if potential_siret:
                siret_value = potential_siret.group()
                _logger.info(f"Found potential SIRET: {siret_value}")
                if siret.validate(siret_value):
                    _logger.info(f"Found valid SIRET: {siret_value}")
                    return "siret", siret_value
                else:
                    _logger.info(f"Invalid SIRET: {siret_value}")
        except Exception as e:
            _logger.debug(f"Error validating SIRET: {str(e)}")

        # Then try to find a SIREN (9 digits)
        try:
            potential_siren = re.search(r"\d{9}", clean_name)
            if potential_siren:
                siren_value = potential_siren.group()
                _logger.info(f"Found potential SIREN: {siren_value}")
                if siren.validate(siren_value):  # Using siren validator directly
                    _logger.info(f"Found valid SIREN: {siren_value}")
                    return "siren", siren_value
                else:
                    _logger.info(f"Invalid SIREN: {siren_value}")
            else:
                _logger.info("No 9-digit number found in name")
        except Exception as e:
            _logger.debug(f"Error validating SIREN: {str(e)}")

        # Finally try to find a VAT number (11 digits)
        try:
            potential_vat = re.search(r"\d{11}", clean_name)
            if potential_vat:
                vat_value = f"FR{potential_vat.group()}"
                _logger.info(f"Found potential VAT: {vat_value}")
                if tva.validate(vat_value):
                    _logger.info(f"Found valid VAT: {vat_value}")
                    return "vat", vat_value
                else:
                    _logger.info(f"Invalid VAT: {vat_value}")
        except Exception as e:
            _logger.debug(f"Error validating VAT: {str(e)}")

        _logger.info(f"No valid identifier found in name: {name}")
        return None, None

    def action_enrich_from_pappers(self):
        """Button action to manually enrich partner data from SIREN/SIRET"""
        self.ensure_one()
        
        # Check if partner has a SIREN code directly in the field
        siren_value = self.siren_pappers or self.siret_pappers
        
        if not siren_value:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Warning'),
                    'message': _('No SIREN or SIRET found for this partner.'),
                    'type': 'warning',
                }
            }

        # If we have a SIRET, extract the SIREN (first 9 digits)
        if len(str(siren_value)) == 14:
            siren_value = str(siren_value)[:9]
        
        # Validate the SIREN
        try:
            if not siren.validate(siren_value):
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Error'),
                        'message': _('Invalid SIREN: %s') % siren_value,
                        'type': 'danger',
                    }
                }
        except Exception as e:
            _logger.error(f"Error validating SIREN {siren_value}: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Error validating SIREN: %s') % str(e),
                    'type': 'danger',
                }
            }

        try:
            pappers_api = self.env["pappers.api"]
            company_data = pappers_api.get_company_details(siren_value)
            
            if company_data:
                formatted_data = self.format_data_company(company_data)
                representatives = self._get_value_from_dict(company_data, "representants")
                if representatives:
                    representative_ids = []
                    for representative in representatives:
                        representative_data = self.format_data_company(representative)
                        representative_data['company_type'] ='person'
                        # Ensure the representative has a name before creating
                        if representative_data.get('name'):
                            representative_id = self.env['res.partner'].create(representative_data)
                            representative_ids.append(representative_id.id)
                        else:
                            _logger.warning(f"Skipping representative without name: {representative}")
                    
                    if representative_ids:
                        self.child_ids = [(4, rid) for rid in representative_ids]
               
                if formatted_data:
                    self.write(formatted_data)
                    template_values = {
                        "flavor_text": _("Partner enriched with Pappers data from SIREN: %s") % siren_value,
                    }
                    self.message_post_with_source(
                        "iap_mail.enrich_company",
                        render_values=template_values,
                        subtype_xmlid="mail.mt_note",
                    )
                    _logger.info(f"Successfully enriched partner {self.name} with SIREN {siren_value}")
                    
                    # Refresh the Odoo page after successful enrichment
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'reload',
                        'params': {
                            'message': _('Partner successfully enriched with Pappers data!'),
                            'type': 'success',
                            'title': _('Success'),
                        }
                    }
                else:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Warning'),
                            'message': _('No data could be formatted from Pappers response.'),
                            'type': 'warning',
                        }
                    }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Warning'),
                        'message': _('No company data found for SIREN: %s') % siren_value,
                        'type': 'warning',
                    }
                }
        except Exception as e:
            _logger.error(f"Error enriching partner {self.name} with SIREN {siren_value}: {str(e)}", exc_info=True)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Error enriching partner: %s') % str(e),
                    'type': 'danger',
                }
            }
    