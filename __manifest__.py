# -*- coding: utf-8 -*-
{
    'name': 'Window Cart Schedule Import',
    'version': '18.0.1.0.0',
    'category': 'Website/eCommerce',
    'summary': 'B2B window schedule upload on cart page',
    'description': """
Window Cart Schedule Import
===========================
* B2B-only feature to upload XLSX/CSV window schedules on /shop/cart
* Parses schedule rows (width, height, system, attributes, qty, etc.)
* Resolves products and attributes automatically
* Normalizes units (in, mm, cm) to inches
* Computes prices using window.configurator.price.service
* Adds configured products to cart using same logic as window_configurator
* Redirects back to cart with all schedule lines added
    """,
    'author': 'Alumen',
    'depends': [
        'website_sale',           # cart & checkout
        'portal',                 # logged-in user handling
        'window_configurator',    # pricing service + add_to_cart logic
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/res_partner_views.xml',
        'views/website_cart_import_templates.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}

