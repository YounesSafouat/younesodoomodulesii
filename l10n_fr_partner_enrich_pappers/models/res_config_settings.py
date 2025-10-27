from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    module_l10n_fr_partner_enrich_pappers = fields.Boolean(
        string="French Company Data Enrichment",
        config_parameter="l10n_fr_partner_enrich_pappers.module_l10n_fr_partner_enrich_pappers",
        help="Enrich partner data with French company information from Pappers.",
    )
    pappers_api_key = fields.Char(
        string="Pappers API Key",
        config_parameter="l10n_fr_partner_enrich_pappers.api_key",
        help="API key for Pappers service",
    )
    pappers_api_url = fields.Char(
        string="Pappers API URL",
        config_parameter="l10n_fr_partner_enrich_pappers.api_url",
        help="Base URL for Pappers API (e.g., https://api.pappers.fr/v2)",
        default="https://api.pappers.fr/v2",
    )
    pappers_api_remaining_credits = fields.Integer(
        string="Remaining Credits",
        config_parameter="l10n_fr_partner_enrich_pappers.remaining_credits",
        help="Remaining credits for Pappers service",
        readonly=True,
    )
    pappers_hide_tab = fields.Boolean(
        string="Hide Pappers Tab",
        config_parameter="l10n_fr_partner_enrich_pappers.hide_tab",
        help="Hide the Pappers information tab in partner form view",
    )
    pappers_document = fields.Boolean(
        string="Rapport financier", config_parameter="l10n_fr_partner_enrich_pappers.pappers_document",
        default=False,
    )

