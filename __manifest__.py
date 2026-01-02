# -*- coding: utf-8 -*-
{
     'name': 'Entrpryz Construction BOQ Control',
     'version': '1.0',
     'category': 'Construction/Project Management',
     'summary': 'Construction BOQ, Budget Control, and Project Costing',
     'description': """
          Entrpryz Construction BOQ Control Module
          ========================================
          [cite_start]Implements tight control over project cost consumption via formal BOQ[cite: 6].
          
          Key Features:
          - [cite_start]Formal BOQ as budget authority [cite: 5]
          - [cite_start]Tight control over project cost consumption [cite: 6]
          - [cite_start]Clear linkage between BOQ, procurement, inventory, accounting, and billing [cite: 7]
          - [cite_start]Accurate budget vs actual and project profitability reporting [cite: 8]
          - [cite_start]Support for BOQ revisions and variations [cite: 9]
     """,
     'author': 'ELB Marketing & Developers',
     'website': 'https://www.entrpryz.com',
     'depends': [
          'base',
          'project',    # Required for Project linking 
          'analytic',   # Required for Cost Centers 
          'purchase',   # Required for PO Integration 
          'stock',      # Required for Inventory Moves 
          'account',    # Required for Financial Entries 
          # 'hr_timesheet', # Optional: labor costing 
     ],
     'data': [
          # We will add security and views here in later tasks
          # 'security/ir.model.access.csv',
          'views/boq_views.xml',
     ],
     'installable': True,
     'application': True,
     'license': 'LGPL-3',
}