# __manifest__.py
# -*- coding: utf-8 -*-
{
    'name': 'Entrpryz Construction BOQ',
    'version': '1.0',
    'category': 'Construction',
    'summary': 'Construction BOQ Management',
    'author': 'ELB Marketing',
    'website': 'https://entrpryz.com',
    # Added 'stock_account' to support valuation overrides
    'depends': ['base', 'project', 'purchase', 'stock', 'stock_account', 'account', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/project_task_views.xml',
        'views/boq_views.xml',
        'views/purchase_views.xml',
        'views/stock_views.xml',
        'views/account_move_views.xml',
        'views/boq_report_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}