# -*- coding: utf-8 -*-
{
    'name': "Stripe Integration",
    'summary': "Integration with Stripe payment gateway",
    'description': """
    Stripe Integration Module
    =========================
    
    This module integrates Odoo with Stripe payment gateway.
    """,
    'author': "Blackswantechnology",
    'website': "https://agence-blackswan.com/",
    'category': 'Accounting/Payment',
    'version': '1.0.0',
    'depends': ['base', 'account', 'sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/sale_order_views.xml',
        'views/sale_portal_templates.xml',
        'views/res_config_settings.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}