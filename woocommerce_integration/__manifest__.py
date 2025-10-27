# -*- coding: utf-8 -*-
{
    'name': 'WooCommerce Integration',
    'version': '1.0.0',
    'category': 'Sales',
    'summary': 'Integration between Odoo and WooCommerce',
    'description': """
WooCommerce Integration
======================

This module provides integration between Odoo and WooCommerce:
- Sync products from WooCommerce to Odoo
- Manage WooCommerce connections
- Import products with attributes and images
- Support for multiple WooCommerce stores

Features:
---------
* WooCommerce API connection management
* Product synchronization (import from WooCommerce)
* Product mapping and attribute handling
* Bulk import operations
* Connection testing
""",
    'author': 'NELY',
    'website': 'https://nely.ma',
    'images': ['static/description/logo.svg'],
    'depends': [
        'base',
        'product',
        'sale',
        'stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/groups.xml',
        'data/ir_cron_data.xml',
        'views/woocommerce_connection_views.xml',
        'views/woocommerce_product_views.xml',
        'views/woocommerce_product_image_views.xml',
        'views/woocommerce_category_views.xml',
        'views/woocommerce_category_mapping_wizard_views.xml',
        'views/odoo_to_woocommerce_wizard_views.xml',
        'views/woocommerce_import_wizard_views.xml',
        'views/woocommerce_conflict_resolution_wizard_views.xml',
        'views/woocommerce_field_mapping_views.xml',
        'views/product_template_views.xml',
        'views/menu.xml',
        'views/woocommerce_order_webhook_views.xml',
        # 'views/res_config_settings.xml',  # Temporarily disabled
    ],
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}
