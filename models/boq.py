# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class ConstructionBOQ(models.Model):
    _name = 'construction.boq'
    _description = 'Construction Bill of Quantities'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    # ==========================================================================
    #                                  FIELDS
    # ==========================================================================
    
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
        tracking=True
    )
    
    analytic_account_id = fields.Many2one(
        'account.analytic.account', 
        string='Analytic Account', 
        required=True, 
        tracking=True
    )
    
    company_id = fields.Many2one(
        'res.company', 
        string='Company', 
        required=True, 
        default=lambda self: self.env.company
    )

    version = fields.Integer(
        string='Version', 
        default=1, 
        required=True, 
        readonly=True, 
        copy=False
    )
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('locked', 'Locked'),
        ('closed', 'Closed')
    ], string='Status', default='draft', required=True, tracking=True, copy=False)

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

    currency_id = fields.Many2one(
        'res.currency', 
        related='company_id.currency_id', 
        string='Currency', 
        readonly=True
    )
    
    boq_line_ids = fields.One2many(
        'construction.boq.line', 
        'boq_id', 
        string='BOQ Lines'
    )
    
    total_budget = fields.Monetary(
        string='Total Budget', 
        compute='_compute_total_budget', 
        currency_field='currency_id', 
        store=True, 
        tracking=True
    )

    # ==========================================================================
    #                            COMPUTE METHODS
    # ==========================================================================

    @api.depends('boq_line_ids.budget_amount', 'currency_id')
    def _compute_total_budget(self):
        for rec in self:
            rec.total_budget = sum(rec.boq_line_ids.mapped('budget_amount'))

    # ==========================================================================
    #                            ONCHANGE METHODS
    # ==========================================================================

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.project_id and self.project_id.analytic_account_id:
            self.analytic_account_id = self.project_id.analytic_account_id

    # ==========================================================================
    #                            WORKFLOW ACTIONS
    # ==========================================================================

    def action_submit(self):
        """ Task 5.2: Change state to 'submitted' """
        for rec in self:
            if not rec.boq_line_ids:
                 raise ValidationError(_('You cannot submit a BOQ with no lines.'))
            rec.write({'state': 'submitted'})

    def action_approve(self):
        """ Task 5.3: Change state to 'approved' """
        self._check_boq_before_approval()  # Run constraint check explicitly
        for rec in self:
            rec.write({
                'state': 'approved',
                'approval_date': fields.Date.today(),
                'approved_by': self.env.user.id
            })

    def action_lock(self):
        """ Change state to 'locked' (Enables consumption) """
        for rec in self:
            rec.write({'state': 'locked'})

    def action_close(self):
        """ Change state to 'closed' """
        for rec in self:
            rec.write({'state': 'closed'})

    # ==========================================================================
    #                              CONSTRAINTS
    # ==========================================================================

    @api.constrains('state')
    def _check_boq_before_approval(self):
        """ Task 5.4: Prevent approval if BOQ has no lines """
        for boq in self:
            if boq.state == 'approved' and not boq.boq_line_ids:
                raise ValidationError(_('BOQ cannot be approved without BOQ lines.'))

    _sql_constraints = [
        ('uniq_project_version', 'unique(project_id, version)', 'A BOQ with this version already exists for this project.'),
        ('uniq_project_state', 'unique(project_id, state)', 'Only one BOQ can be in this state for the project.')
    ]


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

    # ==========================================================================
    #                                  FIELDS
    # ==========================================================================

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
        domain="[('boq_id', '=', boq_id)]"
    )
    
    product_id = fields.Many2one(
        'product.product', 
        string='Product', 
        domain="[('company_id', 'in', (company_id, False))]"
    )
    
    company_id = fields.Many2one(
        related='boq_id.company_id', 
        string='Company', 
        store=True, 
        readonly=True
    )
    
    currency_id = fields.Many2one(
        related='company_id.currency_id', 
        string='Currency', 
        readonly=True
    )
    
    sequence = fields.Integer(string='Sequence', default=10)
    
    display_type = fields.Selection(
        [('line_section', "Section"), ('line_note', "Note")], 
        default=False
    )

    description = fields.Text(string='Description', required=True)
    
    cost_type = fields.Selection([
        ('material', 'Material'), 
        ('labor', 'Labor'),
        ('subcontract', 'Subcontract'), 
        ('service', 'Service'),
        ('overhead', 'Overhead')], 
        string='Cost Type', 
        required=True, 
        default='material'
    )
    
    quantity = fields.Float(string='Quantity', default=1.0, required=True)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure', required=True)
    
    estimated_rate = fields.Monetary(
        string='Rate', 
        currency_field='currency_id', 
        default=0.0, 
        required=True
    )
    
    budget_amount = fields.Monetary(
        string='Budget Amount', 
        compute='_compute_budget_amount', 
        currency_field='currency_id', 
        store=True
    )

    # REMOVED: domain="..." parameter that caused the crash.
    # The domain is now applied in the XML view.
    expense_account_id = fields.Many2one(
        'account.account', 
        string='Expense Account', 
        required=True
    )

    # ==========================================================================
    #                            COMPUTE & ONCHANGE
    # ==========================================================================

    @api.depends('quantity', 'estimated_rate')
    def _compute_budget_amount(self):
        for rec in self:
            rec.budget_amount = rec.quantity * rec.estimated_rate

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.name
            self.uom_id = self.product_id.uom_id
            self.estimated_rate = self.product_id.standard_price

    # ==========================================================================
    #                              CONSTRAINTS
    # ==========================================================================

    @api.constrains('boq_id', 'product_id', 'quantity', 'estimated_rate', 'description')
    def _prevent_edit_on_locked_boq(self):
        """ Task 5.5: Prevent editing BOQ lines if state is approved or locked """
        for line in self:
            if line.boq_id.state in ('approved', 'locked', 'closed'):
                raise ValidationError(_('Approved/Locked BOQs cannot be modified.'))

    _sql_constraints = [
        ('chk_qty_positive', 'CHECK(quantity > 0)', 'Quantity must be positive.'),
        ('chk_amount_positive', 'CHECK(budget_amount >= 0)', 'Budget amount cannot be negative.')
    ]