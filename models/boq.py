# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class ConstructionBOQ(models.Model):
     _name = 'construction.boq'
     _description = 'Construction Bill of Quantities'
     _inherit = ['mail.thread', 'mail.activity.mixin'] # Enables chatter and audit trail
     _order = 'id desc'

     # -- Basic Identifier Fields --
     name = fields.Char(
          string='BOQ Reference', 
          required=True, 
          copy=False, 
          readonly=True, 
          default='New',
          tracking=True
     )    

     project_id = fields.Many2one(
          'project.project', 
          string='Project', 
          required=True, 
          tracking=True,
          domain="[('company_id', '=', company_id)]" 
     )

     analytic_account_id = fields.Many2one(
          'account.analytic.account', 
          string='Analytic Account', 
          required=True,
          tracking=True,
          help="The cost center for this project."
     )

     company_id = fields.Many2one(
          'res.company', 
          string='Company', 
          required=True, 
          default=lambda self: self.env.company
     )

     # -- Task 2.4: Control Fields --
     version = fields.Integer(
          string='Version', 
          default=1, 
          required=True, 
          readonly=True, 
          copy=False,
          help="Incremental version number for BOQ revisions."
     )

     state = fields.Selection([
          ('draft', 'Draft'),
          ('submitted', 'Submitted'),
          ('approved', 'Approved'),
          ('locked', 'Locked'),   # Consumption allowed state
          ('closed', 'Closed')
     ], string='Status', default='draft', required=True, tracking=True, copy=False)

     # -- Task 2.5: Audit Fields --
     approval_date = fields.Date(
          string='Approval Date', 
          readonly=True, 
          copy=False, 
          tracking=True
     )

     approved_by = fields.Many2one(
          'res.users', 
          string='Approved By', 
          readonly=True, 
          copy=False, 
          tracking=True
     )

     # -- Logic to auto-fill Analytic Account from Project --
     @api.onchange('project_id')
     def _onchange_project_id(self):
          if self.project_id and self.project_id.analytic_account_id:
               self.analytic_account_id = self.project_id.analytic_account_id