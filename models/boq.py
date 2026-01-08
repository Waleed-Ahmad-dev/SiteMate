# models/boq.py
# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

class ConstructionBOQ(models.Model):
    _name = 'construction.boq'
    _description = 'Construction Bill of Quantities'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    # -- Header Fields --
    name = fields.Char(string='BOQ Reference', required=True, copy=False, default='New', tracking=True)
    active = fields.Boolean(string='Active', default=True, help="Set to False to hide old versions.")
    
    project_id = fields.Many2one('project.project', string='Project', required=True, tracking=True)
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account', required=True, tracking=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    
    # -- Versioning Fields --
    version = fields.Integer(string='Version', default=1, required=True, readonly=True, copy=False)
    previous_boq_id = fields.Many2one('construction.boq', string='Previous Version', readonly=True, copy=False)
    
    # State: Note that we removed readonly logic in the View, so we rely on the Python logic to handle "locking"
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
    
    revision_ids = fields.One2many('construction.boq.revision', 'original_boq_id', string='Revision History')

    @api.depends('boq_line_ids.budget_amount', 'currency_id')
    def _compute_total_budget(self):
        for rec in self:
            rec.total_budget = sum(rec.boq_line_ids.mapped('budget_amount'))

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.project_id and self.project_id.account_id:
            self.analytic_account_id = self.project_id.account_id

    # -- Workflow Actions --
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

    def action_view_history(self):
        """ Smart button action to see archived/previous versions """
        self.ensure_one()
        return {
            'name': _('Version History'),
            'type': 'ir.actions.act_window',
            'res_model': 'construction.boq',
            'view_mode': 'list,form',
            # Show all previous versions linked to this project, excluding self
            'domain': [('project_id', '=', self.project_id.id), ('id', '!=', self.id)],
            'context': {'active_test': False}, 
        }

    # -------------------------------------------------------------------------
    # AUTOMATIC VERSIONING LOGIC (COPY-ON-WRITE)
    # -------------------------------------------------------------------------

    def create_revision_snapshot(self):
        """
        1. Copies the CURRENT data (before edit) to a new 'Archived' record.
        2. Updates the CURRENT record to be the new Version (N+1).
        """
        for boq in self:
            if boq.state not in ['approved', 'locked']:
                continue
            
            # A. Create the Snapshot (The "Old" Version)
            # We copy the current BOQ. The copy mechanism will duplicate the lines automatically.
            history_name = f"{boq.name} (v{boq.version})"
            
            # Context 'revision_copy' prevents infinite recursion in create/write overrides
            history_boq = boq.with_context(revision_copy=True, mail_create_nosubscribe=True).copy({
                'name': history_name,
                'active': False,         # Archive it
                'state': 'locked',       # Lock it
                'version': boq.version,  # Keep the old version number
                'previous_boq_id': boq.previous_boq_id.id, # Link to the one before that
            })

            # B. Log the snapshot in the separate Revision History Table (Audit Trail)
            self.env['construction.boq.revision'].create({
                'original_boq_id': history_boq.id, # The snapshot is the "Original" now
                'new_boq_id': boq.id,              # The current one is the "New" one
                'revision_reason': "Automatic revision on modification.",
                'approved_by': boq.approved_by.id,
                'approval_date': boq.approval_date,
            })

            # C. Update the CURRENT Record to be the New Version
            # We do this using SQL to avoid triggering the 'write' method again recursively
            new_version = boq.version + 1
            
            # We normally reset state to draft so it can be re-approved. 
            # If you want it to stay approved, remove 'state': 'draft'.
            # Given the strict control, modifying a budget usually requires re-approval.
            boq_vals = {
                'version': new_version,
                'previous_boq_id': history_boq.id,
                'state': 'draft', # Reset to draft to force re-approval of changes
                'approval_date': False,
                'approved_by': False,
            }
            
            # Use super write to update metadata without triggering our override logic again
            super(ConstructionBOQ, boq).write(boq_vals)
            
            # Post message
            boq.message_post(body=f"Auto-Revision: Content modified. Archived v{boq.version-1} and created v{boq.version}.")

    def write(self, vals):
        """
        Override Write to detect changes in Approved/Locked BOQs.
        """
        # If we are just copying for revision, skip logic
        if self.env.context.get('revision_copy'):
            return super(ConstructionBOQ, self).write(vals)

        # Fields that should NOT trigger a revision (technical fields or status updates)
        ignore_fields = ['message_follower_ids', 'state', 'approval_date', 'approved_by', 'active', 'total_budget']
        
        # Check if incoming vals contain actual business data changes
        has_business_changes = any(f not in ignore_fields for f in vals)

        if has_business_changes:
            for boq in self:
                if boq.state in ['approved', 'locked']:
                    # TRIGGER THE SNAPSHOT BEFORE WRITING THE NEW VALUES
                    boq.create_revision_snapshot()

        return super(ConstructionBOQ, self).write(vals)

    # -------------------------------------------------------------------------
    # CONSTRAINTS
    # -------------------------------------------------------------------------

    @api.constrains('state')
    def _check_boq_before_approval(self):
        for boq in self:
            if boq.state == 'approved' and not boq.boq_line_ids:
                raise ValidationError(_('BOQ cannot be approved without BOQ lines.'))

    def _check_one_active_boq(self):
        for rec in self:
            domain = [
                ('project_id', '=', rec.project_id.id), 
                ('state', 'in', ['approved', 'locked']), 
                ('id', '!=', rec.id),
                ('active', '=', True)
            ]
            if self.search_count(domain) > 0:
                raise ValidationError(_('There is already an active (Approved or Locked) BOQ for this project.'))

    _sql_constraints = [
        ('uniq_project_version', 'unique(project_id, version)', 'A BOQ with this version already exists for this project.')
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

    boq_id = fields.Many2one('construction.boq', string='BOQ Reference', required=True, ondelete='cascade', index=True)
    section_id = fields.Many2one('construction.boq.section', string='Section', domain="[('boq_id', '=', boq_id)]")
    product_id = fields.Many2one('product.product', string='Product', domain="[('company_id', 'in', (company_id, False))]")
    
    task_id = fields.Many2one('project.task', string='Task', domain="[('project_id', '=', parent.project_id)]")
    activity_code = fields.Char(string='Activity Code')

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

    analytic_distribution = fields.Json(string='Analytic Distribution')
    analytic_precision = fields.Integer(store=False, default=2)

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
            account = self.product_id.property_account_expense_id or self.product_id.categ_id.property_account_expense_categ_id
            if not account:
                raise UserError(_("No Expense Account defined for product '%s'.") % self.product_id.name)
            self.expense_account_id = account.id

    @api.onchange('task_id')
    def _onchange_task_id(self):
        if self.task_id and self.task_id.activity_code:
            self.activity_code = self.task_id.activity_code

    @api.constrains('analytic_account_id', 'boq_id')
    def _check_project_alignment(self):
        for rec in self:
            if rec.boq_id.analytic_account_id and rec.analytic_account_id:
                if rec.boq_id.analytic_account_id != rec.analytic_account_id:
                    raise ValidationError(_('BOQ Line analytic account must match the Project analytic account.'))

    def check_consumption(self, qty, amount):
        self.ensure_one()
        if not self.allow_over_consumption:
            if qty > self.remaining_quantity + 0.0001:
                 raise ValidationError(_('BOQ Quantity Exceeded for %s.') % self.name)
            if amount > self.remaining_amount + 0.01:
                 raise ValidationError(_('BOQ Budget Exceeded for %s.') % self.name)

    # -------------------------------------------------------------------------
    # PROPAGATE VERSIONING FROM LINE CHANGES
    # -------------------------------------------------------------------------
    
    @api.model_create_multi
    def create(self, vals_list):
        # Identify BOQ IDs being modified
        boq_ids = set()
        for vals in vals_list:
            if vals.get('boq_id'):
                boq_ids.add(vals['boq_id'])
        
        if boq_ids:
            boqs = self.env['construction.boq'].browse(list(boq_ids))
            # Trigger snapshot if parent is approved/locked
            if not self.env.context.get('revision_copy'):
                boqs.filtered(lambda b: b.state in ['approved', 'locked']).create_revision_snapshot()

        return super(ConstructionBOQLine, self).create(vals_list)

    def write(self, vals):
        if not self.env.context.get('revision_copy'):
            # Group lines by boq_id
            boqs = self.mapped('boq_id')
            # Trigger snapshot on parents
            boqs.filtered(lambda b: b.state in ['approved', 'locked']).create_revision_snapshot()
            
        return super(ConstructionBOQLine, self).write(vals)

    def unlink(self):
        if not self.env.context.get('revision_copy'):
            boqs = self.mapped('boq_id')
            boqs.filtered(lambda b: b.state in ['approved', 'locked']).create_revision_snapshot()
            
        return super(ConstructionBOQLine, self).unlink()

    _sql_constraints = [
        ('chk_qty_positive', 'CHECK(quantity > 0)', 'Quantity must be positive.'),
        ('chk_amount_positive', 'CHECK(budget_amount >= 0)', 'Budget amount cannot be negative.'),
        ('uniq_boq_product_section_activity', 'unique(boq_id, section_id, product_id, activity_code)', 'Duplicate product in the same section/activity is not allowed.')
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

    def init(self):
        self.env.cr.execute("""
            REVOKE UPDATE, DELETE ON construction_boq_consumption FROM PUBLIC;
        """)