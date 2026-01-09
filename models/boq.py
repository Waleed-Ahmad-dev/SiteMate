# models/boq.py
# -*- coding: utf-8 -*-
import re
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
    
    project_id = fields.Many2one('project.project', string='Project', required=True, tracking=True, help="Select the construction project this BOQ belongs to.")
    # UX: Add placeholder for better usability
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account', required=True, tracking=True, help="Select the analytic account for cost tracking and budget analysis.")
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    
    # -- Versioning Fields --
    version = fields.Integer(string='Version', default=1, required=True, readonly=True, copy=False, help="Version number of the BOQ, incremented on revision.")
    previous_boq_id = fields.Many2one('construction.boq', string='Previous Version', readonly=True, copy=False)
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('locked', 'Locked'),
        ('closed', 'Closed')
    ], string='Status', default='draft', required=True, tracking=True, copy=False, help="Current status of the BOQ workflow.")
    
    approval_date = fields.Date(string='Approval Date', readonly=True, copy=False, tracking=True)
    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True, copy=False, tracking=True)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', string='Currency', readonly=True)
    
    boq_line_ids = fields.One2many('construction.boq.line', 'boq_id', string='BOQ Lines')
    total_budget = fields.Monetary(string='Total Budget', compute='_compute_total_budget', currency_field='currency_id', store=True, tracking=True)
    
    revision_ids = fields.One2many('construction.boq.revision', 'original_boq_id', string='Revisions (Technical)', copy=False)
    
    display_revision_ids = fields.Many2many('construction.boq.revision', compute='_compute_display_revision_ids', string='Revision History')

    @api.depends('project_id', 'revision_ids')
    def _compute_display_revision_ids(self):
        for rec in self:
            rec.display_revision_ids = self.env['construction.boq.revision'].search([
                '|', ('original_boq_id.project_id', '=', rec.project_id.id),
                     ('new_boq_id.project_id', '=', rec.project_id.id)
            ])

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
        self.ensure_one()
        return {
            'name': _('Version History'),
            'type': 'ir.actions.act_window',
            'res_model': 'construction.boq',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.project_id.id), ('id', '!=', self.id)],
            'context': {'active_test': False}, 
        }

    def action_revise(self):
        self.create_revision_snapshot()
        return True

    # -------------------------------------------------------------------------
    # COPY-ON-WRITE (AUTO VERSIONING) LOGIC
    # -------------------------------------------------------------------------

    def create_revision_snapshot(self):
        for boq in self:
            # FIX: Included 'submitted' in the check so versioning works immediately after submission
            if boq.state not in ['submitted', 'approved', 'locked']:
                continue
            
            # 1. Clean Name Logic
            base_name = re.sub(r' \(v\d+\)$', '', boq.name)
            history_name = f"{base_name} (v{boq.version})"
            
            # 2. Create the snapshot (Copy)
            history_boq = boq.with_context(revision_copy=True, mail_create_nosubscribe=True).copy({
                'name': history_name,
                'active': False,         # Archive it
                'state': 'locked',       # Lock it
                'version': boq.version,  # Keep old version number
                'previous_boq_id': boq.previous_boq_id.id, 
            })

            # 3. Create Audit Trail Entry
            self.env['construction.boq.revision'].create({
                'original_boq_id': history_boq.id, 
                'new_boq_id': boq.id,              
                'revision_reason': "Auto-revision due to modification.",
                'approved_by': boq.approved_by.id,
                'approval_date': boq.approval_date,
            })

            # 4. UPGRADE THE CURRENT RECORD
            new_version = boq.version + 1
            new_name = f"{base_name} (v{new_version})"
            
            boq_vals = {
                'version': new_version,
                'name': new_name, 
                'previous_boq_id': history_boq.id,
                'state': 'draft', 
                'approval_date': False,
                'approved_by': False,
            }
            
            # Use super() to write these values to avoid triggering the 'write' recursion
            super(ConstructionBOQ, boq).write(boq_vals)
            
            # Log it
            boq.message_post(body=f"Content modified. Archived v{boq.version-1} and upgraded to v{boq.version}.")

    def write(self, vals):
        if self.env.context.get('revision_copy'):
            return super(ConstructionBOQ, self).write(vals)

        ignore_fields = [
            'message_follower_ids', 'state', 'approval_date', 'approved_by', 
            'active', 'total_budget', 'previous_boq_id', 'revision_ids', 
            'display_revision_ids', 'write_date', 'write_uid', 'name'
        ]
        
        has_business_changes = any(f not in ignore_fields for f in vals)

        if has_business_changes:
            for boq in self:
                if boq.state in ['submitted', 'approved', 'locked']:
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

    @api.constrains('project_id', 'version', 'active')
    def _check_unique_active_version(self):
        for rec in self:
            if rec.active:
                domain = [
                    ('project_id', '=', rec.project_id.id),
                    ('version', '=', rec.version),
                    ('active', '=', True),
                    ('id', '!=', rec.id)
                ]
                if self.search_count(domain) > 0:
                    raise ValidationError(_('An active BOQ with this version already exists for this project.'))

    def _check_one_active_boq(self):
        for rec in self:
            domain = [
                ('project_id', '=', rec.project_id.id), 
                ('state', 'in', ['approved', 'locked']), 
                ('id', '!=', rec.id),
                ('active', '=', True)
            ]
            if self.search_count(domain) > 0:
                raise ValidationError(_('There is already an active (Approved or Locked) BOQ for this project. Please revise the existing one.'))


class ConstructionBOQSection(models.Model):
    _name = 'construction.boq.section'
    _description = 'BOQ Section'
    _order = 'sequence, id'

    # UPDATED: Removed boq_id to make sections independent/global
    name = fields.Char(string='Section Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)


class ConstructionBOQLine(models.Model):
    _name = 'construction.boq.line'
    _description = 'BOQ Line Item'
    _order = 'sequence, id'

    boq_id = fields.Many2one('construction.boq', string='BOQ Reference', required=True, ondelete='cascade', index=True)
    
    # UPDATED: Removed domain linked to boq_id so global sections can be selected
    section_id = fields.Many2one('construction.boq.section', string='Section')
    
    product_id = fields.Many2one('product.product', string='Product', domain="[('company_id', 'in', (company_id, False))]")
    
    task_id = fields.Many2one('project.task', string='Task', domain="[('project_id', '=', parent.project_id)]")
    activity_code = fields.Char(string='Activity Code', help="Code used to link this BOQ line to a specific project task or schedule activity.")

    company_id = fields.Many2one('res.company', related='boq_id.company_id', string='Company', store=True, readonly=True)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', string='Currency', readonly=True)
    sequence = fields.Integer(string='Sequence', default=10)
    display_type = fields.Selection([('line_section', 'Section'), ('line_note', 'Note')], default=False)
    name = fields.Char(string='Description', required=True)
    description = fields.Text(string='Long Description')
    cost_type = fields.Selection([('material', 'Material'), ('labor', 'Labor'), ('subcontract', 'Subcontract'), ('service', 'Service'), ('overhead', 'Overhead')], string='Cost Type', required=True, default='material', help="Classifies the type of cost for reporting and analysis.")
    quantity = fields.Float(string='Quantity', default=1.0, required=True)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure', required=True)
    estimated_rate = fields.Monetary(string='Rate', currency_field='currency_id', default=0.0, required=True)
    budget_amount = fields.Monetary(string='Budget Amount', compute='_compute_budget_amount', currency_field='currency_id', store=True)
    
    expense_account_id = fields.Many2one('account.account', string='Expense Account', required=True, check_company=True)
    analytic_account_id = fields.Many2one('account.analytic.account', related='boq_id.analytic_account_id', string='Analytic Account', store=True)

    analytic_distribution = fields.Json(string='Analytic Distribution', help="Distribute costs across multiple analytic accounts.")
    analytic_precision = fields.Integer(store=False, default=2)

    consumed_quantity = fields.Float(string='Consumed Qty', compute='_compute_consumption', store=True)
    consumed_amount = fields.Monetary(string='Consumed Amount', compute='_compute_consumption', currency_field='currency_id', store=True)
    remaining_quantity = fields.Float(string='Remaining Qty', compute='_compute_consumption', store=True)
    remaining_amount = fields.Monetary(string='Remaining Amount', compute='_compute_consumption', currency_field='currency_id', store=True)
    allow_over_consumption = fields.Boolean(string='Allow Over Consumption', default=False, help="If checked, allows consumption to exceed the budgeted quantity/amount without error.")
    consumption_ids = fields.One2many('construction.boq.consumption', 'boq_line_id', string='Consumptions')

    # UI/UX Helper for Progress Bars
    consumption_percentage = fields.Float(string='Progress', compute='_compute_consumption_percentage', store=False, help="Percentage of budget consumed.")

    @api.depends('quantity', 'estimated_rate')
    def _compute_budget_amount(self):
        for rec in self:
            rec.budget_amount = rec.quantity * rec.estimated_rate

    @api.depends('quantity', 'budget_amount', 'consumption_ids.quantity', 'consumption_ids.amount')
    def _compute_consumption(self):
        # 1. Handle unsaved records (NewIds) - fallback to python loop to ensure correctness
        new_records = self.filtered(lambda r: not isinstance(r.id, int))
        for rec in new_records:
            c_qty = 0.0
            c_amt = 0.0
            for c in rec.consumption_ids:
                c_qty += c.quantity
                c_amt += c.amount

            rec.consumed_quantity = c_qty
            rec.consumed_amount = c_amt
            rec.remaining_quantity = rec.quantity - c_qty
            rec.remaining_amount = rec.budget_amount - c_amt

        # 2. Handle persisted records - use read_group for performance
        real_records = self - new_records
        if real_records:
            # Initialize to 0 first (in case they have no consumptions)
            for rec in real_records:
                rec.consumed_quantity = 0.0
                rec.consumed_amount = 0.0
                rec.remaining_quantity = rec.quantity
                rec.remaining_amount = rec.budget_amount

            # Fetch aggregated data from DB
            data = self.env['construction.boq.consumption'].read_group(
                [('boq_line_id', 'in', real_records.ids)],
                ['boq_line_id', 'quantity', 'amount'],
                ['boq_line_id']
            )
            data_map = {d['boq_line_id'][0]: d for d in data}

            for rec in real_records:
                group = data_map.get(rec.id)
                if group:
                    c_qty = group['quantity']
                    c_amt = group['amount']

                    rec.consumed_quantity = c_qty
                    rec.consumed_amount = c_amt
                    rec.remaining_quantity = rec.quantity - c_qty
                    rec.remaining_amount = rec.budget_amount - c_amt


    @api.depends('consumed_amount', 'budget_amount')
    def _compute_consumption_percentage(self):
        for rec in self:
            if rec.budget_amount > 0:
                rec.consumption_percentage = (rec.consumed_amount / rec.budget_amount)
            else:
                rec.consumption_percentage = 0.0

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
        boq_ids = set()
        for vals in vals_list:
            if vals.get('boq_id'):
                boq_ids.add(vals['boq_id'])
        
        if boq_ids:
            if not self.env.context.get('revision_copy'):
                boqs = self.env['construction.boq'].browse(list(boq_ids))
                boqs.filtered(lambda b: b.state in ['submitted', 'approved', 'locked']).create_revision_snapshot()

        return super(ConstructionBOQLine, self).create(vals_list)

    def write(self, vals):
        if not self.env.context.get('revision_copy'):
            boqs = self.mapped('boq_id')
            boqs.filtered(lambda b: b.state in ['submitted', 'approved', 'locked']).create_revision_snapshot()
            
        return super(ConstructionBOQLine, self).write(vals)

    def unlink(self):
        if not self.env.context.get('revision_copy'):
            boqs = self.mapped('boq_id')
            boqs.filtered(lambda b: b.state in ['submitted', 'approved', 'locked']).create_revision_snapshot()
            
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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Security Fix: Enforce budget limits on direct creation (e.g. via API)
            # This prevents bypassing the check_consumption logic in AccountMove
            if vals.get('boq_line_id'):
                line = self.env['construction.boq.line'].browse(vals['boq_line_id'])
                qty = vals.get('quantity', 0.0)
                amt = vals.get('amount', 0.0)

                # Check limits if positive consumption is added.
                # Negative values (refunds) are allowed to increase remaining budget.
                if qty > 0 or amt > 0:
                    line.check_consumption(qty, amt)

        return super(ConstructionBOQConsumption, self).create(vals_list)

    def init(self):
        self.env.cr.execute("""
            REVOKE UPDATE, DELETE ON construction_boq_consumption FROM PUBLIC;
        """)
