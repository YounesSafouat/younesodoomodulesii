{
    "name": "Enrichissement des données des entreprises françaises avec l'API Pappers",
    'version': '18.0.0.0.1',
    "depends": [
        "base",
        "contacts",
        "crm",
        "sale",
    ],
    "author": "ZENPILOTE",
    "contributors": [
        "Nazaire ADJAKOUN < https://www.linkedin.com/in/nadjakoun/ >",
    ],
    "website": "https://zenpilote.fr",
    "category": "Localization",
    "summary": "Enrichissement des données des entreprises françaises avec l'API Pappers",
    'assets': {
        'web.assets_backend': [
            'l10n_fr_partner_enrich_pappers/static/src/css/sale_order_totals.css',  
        ],
    },
    "description": """
Ce module permet d'enrichir les données des partenaires pour les entreprises françaises en utilisant l'API Pappers.

Fonctionnalités:
- Détection automatique des numéros SIRET/SIREN dans les noms des partenaires
- Récupération des informations légales et administratives
- Nouveaux champs dans la fiche partenaire pour les données des entreprises
- Options de filtrage et de regroupement
- Gestion sécurisée des clés API
- Mappage de champs préconfiguré avec options de personnalisation
    """,
    "license": "LGPL-3",
    "data": [
        "security/ir.model.access.csv",
        "data/pappers_field_mapping_data.xml",
        "views/res_partner.xml",
        "views/res_config_settings.xml",
        "views/pappers_field_mapping_views.xml",
        "data/ir_cron_data.xml",
        "views/webclient_templates.xml",
        "views/crm_lead_views.xml",
        "views/sale_order_views.xml"
    ],
    "auto_install": False,
}
