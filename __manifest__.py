# -*- coding: utf-8 -*-
{
    'name': 'Entrpryz Construction BOQ',
    'version': '1.0',
    'category': 'Construction',
    'summary': 'Construction BOQ Management',
    'author': 'ELB Marketing',
    'website': 'https://entrpryz.com',
    'depends': ['base', 'project', 'purchase', 'stock', 'account', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/boq_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}