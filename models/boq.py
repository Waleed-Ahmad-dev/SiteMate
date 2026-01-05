# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class ConstructionBOQ(models.Model):
    _name = 'construction.boq'
    _description = 'Construction Bill of Quantities'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    # FIX 1: Removed readonly=True so you can rename the BOQ
    name = fields.Char(string='BOQ Reference', required=True, copy=False, default='New', tracking=True)
    
    project_id = fields.Many2one('project.project', string='Project', required=True, tracking=True)
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account', required=True, tracking=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    version = fields.Integer(string='Version', default=1, required=True, readonly=True, copy=False)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('locked', 'Locked'),
        ('closed', 'Closed')
    ], string='Status', default='draft', required=True, tracking=True, copy=False)
    approval_date = fields.Date(string='Approval Date', readonly=True, copy=False, tracking=True)
    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True, copy=False, tracking=True)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', string='Currency', readonly=True)
    boq_line_ids = fields.One2many('construction.boq.line', 'boq_id', string='BOQ Lines')
    total_budget = fields.Monetary(string='Total Budget', compute='_compute_total_budget', currency_field='currency_id', store=True, tracking=True)

    @api.depends('boq_line_ids.budget_amount', 'currency_id')
    def _compute_total_budget(self):
        for rec in self:
            rec.total_budget = sum(rec.boq_line_ids.mapped('budget_amount'))

    @api.onchange('project_id')
    def _onchange_project_id(self):
        # FIX 2: Updated to use 'account_id' which is the correct field name in Odoo 18
        if self.project_id and self.project_id.account_id:
            self.analytic_account_id = self.project_id.account_id

    def action_submit(self):
        for rec in self:
            if not rec.boq_line_ids:
                 raise ValidationError(_('You cannot submit a BOQ with no lines.'))
            rec.write({'state': 'submitted'})

    def action_approve(self):
        self._check_boq_before_approval()
        self._check_one_active_boq()
        for rec in self:
            rec.write({'state': 'approved', 'approval_date': fields.Date.today(), 'approved_by': self.env.user.id})

    def action_lock(self):
        for rec in self:
            rec.write({'state': 'locked'})

    def action_close(self):
        for rec in self:
            rec.write({'state': 'closed'})

    @api.constrains('state')
    def _check_boq_before_approval(self):
        for boq in self:
            if boq.state == 'approved' and not boq.boq_line_ids:
                raise ValidationError(_('BOQ cannot be approved without BOQ lines.'))

    def _check_one_active_boq(self):
        for rec in self:
            domain = [('project_id', '=', rec.project_id.id), ('state', 'in', ['approved', 'locked']), ('id', '!=', rec.id)]
            if self.search_count(domain) > 0:
                raise ValidationError(_('There is already an active (Approved or Locked) BOQ for this project.'))

    _sql_constraints = [('uniq_project_version', 'unique(project_id, version)', 'A BOQ with this version already exists for this project.')]

class ConstructionBOQSection(models.Model):
    _name = 'construction.boq.section'
    _description = 'BOQ Section'
    _order = 'sequence, id'

    name = fields.Char(string='Section Name', required=True)
    boq_id = fields.Many2one('construction.boq', string='BOQ Reference', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)

class ConstructionBOQLine(models.Model):
    _name = 'construction.boq.line'
    _description = 'BOQ Line Item'
    _order = 'sequence, id'

    boq_id = fields.Many2one('construction.boq', string='BOQ Reference', required=True, ondelete='cascade', index=True)
    section_id = fields.Many2one('construction.boq.section', string='Section', domain="[('boq_id', '=', boq_id)]")
    product_id = fields.Many2one('product.product', string='Product', domain="[('company_id', 'in', (company_id, False))]")
    company_id = fields.Many2one('res.company', related='boq_id.company_id', string='Company', store=True, readonly=True)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', string='Currency', readonly=True)
    sequence = fields.Integer(string='Sequence', default=10)
    display_type = fields.Selection([('line_section', 'Section'), ('line_note', 'Note')], default=False)
    name = fields.Char(string='Description', required=True)
    description = fields.Text(string='Long Description')
    cost_type = fields.Selection([('material', 'Material'), ('labor', 'Labor'), ('subcontract', 'Subcontract'), ('service', 'Service'), ('overhead', 'Overhead')], string='Cost Type', required=True, default='material')
    quantity = fields.Float(string='Quantity', default=1.0, required=True)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure', required=True)
    estimated_rate = fields.Monetary(string='Rate', currency_field='currency_id', default=0.0, required=True)
    budget_amount = fields.Monetary(string='Budget Amount', compute='_compute_budget_amount', currency_field='currency_id', store=True)
    expense_account_id = fields.Many2one('account.account', string='Expense Account', required=True, check_company=True)
    analytic_account_id = fields.Many2one('account.analytic.account', related='boq_id.analytic_account_id', string='Analytic Account', store=True)
    consumed_quantity = fields.Float(string='Consumed Qty', compute='_compute_consumption', store=True)
    consumed_amount = fields.Monetary(string='Consumed Amount', compute='_compute_consumption', currency_field='currency_id', store=True)
    remaining_quantity = fields.Float(string='Remaining Qty', compute='_compute_consumption', store=True)
    remaining_amount = fields.Monetary(string='Remaining Amount', compute='_compute_consumption', currency_field='currency_id', store=True)
    allow_over_consumption = fields.Boolean(string='Allow Over Consumption', default=False)
    consumption_ids = fields.One2many('construction.boq.consumption', 'boq_line_id', string='Consumptions')

    @api.depends('quantity', 'estimated_rate')
    def _compute_budget_amount(self):
        for rec in self:
            rec.budget_amount = rec.quantity * rec.estimated_rate

    @api.depends('quantity', 'budget_amount', 'consumption_ids.quantity', 'consumption_ids.amount')
    def _compute_consumption(self):
        for rec in self:
            rec.consumed_quantity = sum(rec.consumption_ids.mapped('quantity'))
            rec.consumed_amount = sum(rec.consumption_ids.mapped('amount'))
            rec.remaining_quantity = rec.quantity - rec.consumed_quantity
            rec.remaining_amount = rec.budget_amount - rec.consumed_amount

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.name = self.product_id.name
            self.description = self.product_id.description_sale or self.product_id.name
            self.uom_id = self.product_id.uom_id
            self.estimated_rate = self.product_id.standard_price

    @api.constrains('boq_id', 'product_id', 'quantity', 'estimated_rate', 'name')
    def _prevent_edit_on_locked_boq(self):
        for line in self:
            if line.boq_id.state in ('approved', 'locked', 'closed'):
                raise ValidationError(_('Approved/Locked BOQs cannot be modified.'))

    @api.constrains('analytic_account_id', 'boq_id')
    def _check_project_alignment(self):
        for rec in self:
            if rec.boq_id.analytic_account_id and rec.analytic_account_id:
                if rec.boq_id.analytic_account_id != rec.analytic_account_id:
                    raise ValidationError(_('BOQ Line analytic account must match the Project analytic account.'))

    _sql_constraints = [
        ('chk_qty_positive', 'CHECK(quantity > 0)', 'Quantity must be positive.'),
        ('chk_amount_positive', 'CHECK(budget_amount >= 0)', 'Budget amount cannot be negative.'),
        ('uniq_boq_product_section', 'unique(boq_id, section_id, product_id)', 'Duplicate product in the same section is not allowed.')
    ]

class ConstructionBOQConsumption(models.Model):
    _name = 'construction.boq.consumption'
    _description = 'BOQ Consumption Ledger'
    _order = 'date desc, id desc'

    boq_line_id = fields.Many2one('construction.boq.line', string='BOQ Line', required=True, ondelete='restrict', index=True)
    source_model = fields.Char(string='Source Model', required=True)
    source_id = fields.Integer(string='Source ID', required=True)
    quantity = fields.Float(string='Quantity Consumed')
    amount = fields.Monetary(string='Amount Consumed', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', related='boq_line_id.currency_id', store=True)
    date = fields.Date(string='Date', default=fields.Date.context_today, required=True)
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user)