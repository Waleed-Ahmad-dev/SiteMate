# ./__manifest__.py
# -*- coding: utf-8 -*-
{
    'name': 'Entrpryz Construction BOQ',
    'version': '18.0.1.0.0',  # Updated for Odoo 18 convention
    'category': 'Construction',
    'summary': 'Construction BOQ Management',
    'author': 'Waleed Ahmad (Shadow Scripter)',
    'website': 'https://www.shadowscripter.online',
    'depends': [
        'base', 'project', 'purchase', 'stock', 'stock_account',
        'account', 'mail', 'analytic'
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'security/construction_security.xml',
        'views/project_task_views.xml',
        'views/boq_views.xml',
        'views/purchase_views.xml',
        'views/stock_views.xml',
        'views/account_move_views.xml',
        'views/boq_report_views.xml',
        'views/boq_line_views.xml', # New file for line views
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}