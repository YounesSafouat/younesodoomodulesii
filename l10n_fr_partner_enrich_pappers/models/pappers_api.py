# -*- coding: utf-8 -*-

import logging
import requests
from odoo import models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

PAPPERS_API_VERSION = "v2"
PAPPERS_TIMEOUT = 10

ENDPOINTS = {
    "recherche": "recherche",  # Pour l'autocomplétion et la recherche
    "entreprise": "entreprise",  # Pour les données détaillées
    "suivi_jetons": "suivi-jetons",  # Pour le suivi des jetons
    "extrait_pappers": "extrait_pappers",    # Ajouté pour corriger le KeyError
}


class PappersAPI(models.AbstractModel):
    _name = "pappers.api"
    _description = "Pappers API Integration"

    @api.model
    def _get_api_key(self):
        """Get the API key from system parameters"""
        api_key = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("l10n_fr_partner_enrich_pappers.api_key")
        )
        if not api_key:
            raise UserError(
                _(
                    "Pappers API key is not configured. Please configure it in the settings."
                )
            )
        return api_key

    @api.model
    def _get_api_url(self):
        """Get the API URL from system parameters"""
        api_url = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("l10n_fr_partner_enrich_pappers.api_url", "https://api.pappers.fr/v2")
        )
        return api_url.rstrip('/')  # Remove trailing slash if present

    def _cron_update_remaining_tokens(self):
        """Cron job to update remaining tokens"""
        try:
            self.get_remaining_tokens()
        except Exception as e:
            _logger.error(f"Failed to update Pappers API remaining tokens: {str(e)}")

    def _make_request(self, endpoint, params=None):
        """Make a request to Pappers API"""
        api_key = self._get_api_key()
        api_url = self._get_api_url()
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        url = f"{api_url}/{endpoint}"

        try:
            response = requests.get(
                url=url, headers=headers, params=params, timeout=PAPPERS_TIMEOUT
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            _logger.error(f"Pappers API error: {str(e)}")
            if hasattr(response, "status_code"):
                if response.status_code == 401:
                    raise UserError(_("Invalid API key or authentication failed"))
                elif response.status_code == 429:
                    raise UserError(_("API rate limit exceeded"))
            raise UserError(_("Failed to connect to Pappers API: %s") % str(e))

    def _make_request_docs(self, endpoint, params=None):
        """Make a request to Pappers API for documents (returns PDF content)"""
        api_key = self._get_api_key()
        api_url = self._get_api_url()
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/pdf",
        }

        url = f"{api_url}/document/{endpoint}"

        try:
            response = requests.get(
                url=url, headers=headers, params=params, timeout=PAPPERS_TIMEOUT
            )
            response.raise_for_status()
            # The response is a PDF (application/pdf), so return the binary content
            if response.headers.get("Content-Type", "").startswith("application/pdf"):
                return response.content
            else:
                _logger.error("Pappers API did not return a PDF document.")
                raise UserError(_("Pappers API did not return a PDF document."))
        except requests.exceptions.RequestException as e:
            _logger.error(f"Pappers API error: {str(e)}")
            if hasattr(e, "response") and e.response is not None:
                if e.response.status_code == 401:
                    raise UserError(_("Invalid API key or authentication failed"))
                elif e.response.status_code == 429:
                    raise UserError(_("API rate limit exceeded"))
            raise UserError(_("Failed to connect to Pappers API: %s") % str(e))

    def search_companies(self, query=None, per_page=10, page=1):
        """Search companies using name or identifiers"""
        params = {
            "q": query,
            "par_page": per_page,
            "page": page,
            # Optimisation : ne récupérer que les champs nécessaires
            "champs": "siren,siret,denomination,siege.code_postal,siege.ville,siege.adresse_ligne_1",
        }
        return self._make_request(ENDPOINTS["recherche"], params)

    def get_company_details(self, identifier):
        """Get detailed information about a company using SIREN or SIRET"""
        params = {}
        if len(identifier) == 14:  # SIRET
            params["siret"] = identifier
        else:  # SIREN
            params["siren"] = identifier

        # Champs de base
        params["champs"] = ",".join([
            "siren",
            "siret",
            "denomination",
            "siege.adresse_ligne_1",
            "siege.adresse_ligne_2",
            "siege.code_postal",
            "siege.ville",
            "siege.pays",
            "forme_juridique",
            "date_creation",
            "capital",
            "devise_capital",
            "numero_rcs",
            "date_immatriculation_rcs",
            "statut_rcs",
            "effectif",
            "objet_social",
            "sites_internet",
            "telephone",
            "email",
            "representants"
        ])

        # Champs supplémentaires pour les contacts
        params["champs_supplementaires"] = ",".join([
            "sites_internet",
            "telephone",
            "email",
            "representants"
        ])

        return self._make_request(ENDPOINTS["entreprise"], params)

    def get_remaining_tokens(self):
        """Get the remaining tokens for the Pappers API account"""
        try:
            response = self._make_request(ENDPOINTS["suivi_jetons"])
            if response and isinstance(response, dict):
                # On ne prend en compte que les jetons pay-as-you-go restants
                remaining_payg = response.get("jetons_pay_as_you_go_restants", 0)
                
                # Mise à jour des paramètres système
                self.env["ir.config_parameter"].sudo().set_param(
                    "l10n_fr_partner_enrich_pappers.remaining_credits",
                    str(remaining_payg)
                )
                return remaining_payg
            return 0
        except Exception as e:
            _logger.error(f"Error getting remaining tokens: {str(e)}")
            return 0

    def search_extraits(self, query=None):
        """Search extraits using name or identifiers and fetch the PDF if available"""
        params = {
            "siren": query,
        }
        # Correction du KeyError: 'extrait_pappers'
        try:
            result = self._make_request_docs(ENDPOINTS.get("rapport_financier", "rapport_financier"), params)
        except Exception as e:
            _logger.error(f"Error during _make_request_docs: {e}")
            # Return a safe empty result structure to avoid further errors
            return {"resultats": []}

        # If a PDF URL is present in the results, fetch the PDF content
        if result and isinstance(result, dict) and result.get('resultats'):
            first_doc = result['resultats'][0]
            pdf_url = first_doc.get('url_pdf')
            if pdf_url:
                try:
                    import requests
                    response = requests.get(pdf_url)
                    if response.status_code == 200:
                        first_doc['pdf_content'] = response.content
                except Exception as e:
                    _logger.error(f"Failed to fetch PDF from {pdf_url}: {e}")
        return result if result else {"resultats": []}