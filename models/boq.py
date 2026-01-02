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

     # -- Control Fields --
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

     # -- Audit Fields --
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

     # -- Financial Fields (Total Budget) --
     currency_id = fields.Many2one(
          'res.currency', 
          related='company_id.currency_id', 
          string='Currency', 
          readonly=True
     )

     total_budget = fields.Monetary(
          string='Total Budget', 
          compute='_compute_total_budget', 
          currency_field='currency_id',
          store=True,
          tracking=True,
          help="Sum of all BOQ Lines"
     )

     # Placeholder for Lines (We will define this fully in Phase 3)
     # boq_line_ids = fields.One2many('construction.boq.line', 'boq_id', string='BOQ Lines')

     @api.depends('currency_id') # We will add 'boq_line_ids.budget_amount' here in Phase 3
     def _compute_total_budget(self):
          for rec in self:
               # Placeholder logic until we create the Lines model
               rec.total_budget = 0.0
               # Future Logic:
               # rec.total_budget = sum(rec.boq_line_ids.mapped('budget_amount'))

     # -- Logic to auto-fill Analytic Account from Project --
     @api.onchange('project_id')
     def _onchange_project_id(self):
          if self.project_id and self.project_id.analytic_account_id:
               self.analytic_account_id = self.project_id.analytic_account_id

     # -- SQL Constraints --
     _sql_constraints = [
          ('uniq_project_version', 
          'unique(project_id, version)', 
          'A BOQ with this version already exists for this project.'),
          
          # Enforces one BOQ per state per project (e.g., only 1 Draft, 1 Approved)
          ('uniq_project_state', 
          'unique(project_id, state)', 
          'Only one BOQ can be in this state for the project.')
     ]

class ConstructionBOQSection(models.Model):
     _name = 'construction.boq.section'
     _description = 'BOQ Section'
     _order = 'sequence, id'

     name = fields.Char(
          string='Section Name', 
          required=True,
          help="e.g. Civil Works, Electrical, Plumbing"
     )

     boq_id = fields.Many2one(
          'construction.boq', 
          string='BOQ Reference', 
          required=True, 
          ondelete='cascade' # If BOQ is deleted, delete sections too
     )

     sequence = fields.Integer(
          string='Sequence', 
          default=10,
          help="Used to order the sections in the report"
     )

class ConstructionBOQLine(models.Model):
     _name = 'construction.boq.line'
     _description = 'BOQ Line Item'
     _order = 'sequence, id'

     # -- Relational Fields --
     boq_id = fields.Many2one(
          'construction.boq', 
          string='BOQ Reference', 
          required=True, 
          ondelete='cascade',
          index=True
     )     

     section_id = fields.Many2one(
          'construction.boq.section', 
          string='Section', 
          domain="[('boq_id', '=', boq_id)]",
          help="Logical grouping (e.g. Civil Works)"
     )

     product_id = fields.Many2one(
          'product.product', 
          string='Product', 
          domain="[('company_id', 'in', (company_id, False))]",
          help="Link to standard Odoo product for auto-completion"
     )

     company_id = fields.Many2one(
          related='boq_id.company_id', 
          string='Company', 
          store=True, 
          readonly=True
     )

     sequence = fields.Integer(string='Sequence', default=10)