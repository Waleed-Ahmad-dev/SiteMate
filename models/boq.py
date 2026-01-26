# -*- coding: utf-8 -*-
import re
from odoo import models, fields, api, _, Command
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
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account', required=True, tracking=True, help="Select the analytic account for cost tracking and budget analysis.")
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    
    # -- [NEW] Quotation Template Import --
    quotation_template_id = fields.Many2one(
        'sale.order.template', 
        string='Import From Template', 
        help="Select a Quotation Template to auto-populate BOQ Lines."
    )

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

    # -------------------------------------------------------------------------
    # [NEW] QUOTATION TEMPLATE LOGIC
    # -------------------------------------------------------------------------
    def _get_lines_from_template(self, template):
        """
        Helper method to map Sale Order Template Lines to BOQ Lines (Command.create).
        Used by both default_get (Initial Load) and onchange (User Selection).
        """
        new_lines = []
        for template_line in template.sale_order_template_line_ids:
            data = {
                'display_type': template_line.display_type,
                'name': template_line.name,
                'sequence': template_line.sequence,
            }

            if not template_line.display_type:
                # It is a product line
                product = template_line.product_id
                
                # Determine Expense Account
                expense_account = product.property_account_expense_id or \
                                  product.categ_id.property_account_expense_categ_id
                
                data.update({
                    'product_id': product.id,
                    'quantity': template_line.product_uom_qty,
                    'uom_id': template_line.product_uom_id.id,
                    # IMPORTANT: BOQ uses Cost (Standard Price), not Sales Price
                    'estimated_rate': product.standard_price, 
                    'expense_account_id': expense_account.id if expense_account else False,
                })
            
            new_lines.append(Command.create(data))
        return new_lines

    @api.model
    def default_get(self, fields_list):
        """
        Override default_get to pre-populate BOQ lines if a quotation_template_id
        is passed in the context (e.g., from the 'Export to BOQ' button).
        """
        res = super(ConstructionBOQ, self).default_get(fields_list)
        
        # Check if we have a template ID in the defaults
        template_id = res.get('quotation_template_id')
        if template_id:
            template = self.env['sale.order.template'].browse(template_id)
            if template:
                # Generate the line commands
                lines = self._get_lines_from_template(template)
                res['boq_line_ids'] = lines
        
        return res

    @api.onchange('quotation_template_id')
    def _onchange_quotation_template_id(self):
        """
        Import lines from the selected Quotation Template into the BOQ.
        """
        if not self.quotation_template_id:
            return

        # Generate new lines using the helper
        new_lines = self._get_lines_from_template(self.quotation_template_id)
        
        # Add new lines to the existing list
        self.boq_line_ids = new_lines

    @api.depends('project_id', 'revision_ids')
    def _compute_display_revision_ids(self):
        if not self:
            self.display_revision_ids = False
            return
            
        project_ids = self.mapped('project_id').ids
        if not project_ids:
            self.display_revision_ids = False
            return
            
        revisions = self.env['construction.boq.revision'].search([
            '|', ('original_boq_id.project_id', 'in', project_ids),
                 ('new_boq_id.project_id', 'in', project_ids)
        ])
        
        revision_map = {}
        for revision in revisions:
            original_project_id = revision.original_boq_id.project_id.id
            revision_map.setdefault(original_project_id, []).append(revision.id)
            new_project_id = revision.new_boq_id.project_id.id
            revision_map.setdefault(new_project_id, []).append(revision.id)
        
        for boq in self:
            revision_ids = revision_map.get(boq.project_id.id, [])
            boq.display_revision_ids = [(6, 0, revision_ids)]

    @api.depends('boq_line_ids.budget_amount', 'currency_id')
    def _compute_total_budget(self):
        for rec in self:
            # [FIX] Only sum actual lines, ignore sections/notes to prevent type errors
            lines = rec.boq_line_ids.filtered(lambda l: not l.display_type)
            rec.total_budget = sum(lines.mapped('budget_amount'))

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.project_id and self.project_id.account_id:
            self.analytic_account_id = self.project_id.account_id

    # -- Workflow Actions --
    def action_submit(self):
        # [FIX] Ensure we have actual product lines, not just sections
        boqs_with_valid_lines = self.filtered(lambda r: r.boq_line_ids.filtered(lambda l: not l.display_type))
        if len(boqs_with_valid_lines) != len(self):
            raise ValidationError(_('You cannot submit a BOQ with no product lines.'))
        
        self.write({'state': 'submitted'})

    def action_approve(self):
        self._check_boq_before_approval()
        self._check_one_active_boq()
        
        self.write({
            'state': 'approved',
            'approval_date': fields.Date.today(),
            'approved_by': self.env.user.id
        })

    def action_lock(self):
        self.write({'state': 'locked'})

    def action_close(self):
        self.write({'state': 'closed'})

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
        boqs_to_revise = self.filtered(
            lambda b: b.state in ['submitted', 'approved', 'locked']
        )
        
        if not boqs_to_revise:
            return
            
        revision_vals_list = []
        boq_update_vals = {}
        messages_to_post = []
        
        for boq in boqs_to_revise:
            base_name = re.sub(r' \(v\d+\)$', '', boq.name)
            history_name = f"{base_name} (v{boq.version})"
            
            history_boq = boq.with_context(revision_copy=True, mail_create_nosubscribe=True).copy({
                'name': history_name,
                'active': False,
                'state': 'locked',
                'version': boq.version,
                'previous_boq_id': boq.previous_boq_id.id,
            })
            revision_vals_list.append({
                'original_boq_id': history_boq.id,
                'new_boq_id': boq.id,
                'revision_reason': "Auto-revision due to modification.",
                'approved_by': boq.approved_by.id,
                'approval_date': boq.approval_date,
            })
            new_version = boq.version + 1
            new_name = f"{base_name} (v{new_version})"
            
            boq_update_vals[boq.id] = {
                'version': new_version,
                'name': new_name,
                'previous_boq_id': history_boq.id,
                'state': 'draft',
                'approval_date': False,
                'approved_by': False,
            }
            
            messages_to_post.append((boq, f"Content modified. Archived v{new_version-1} and upgraded to v{new_version}."))
        
        if revision_vals_list:
            self.env['construction.boq.revision'].create(revision_vals_list)
        
        for boq_id, vals in boq_update_vals.items():
            super(ConstructionBOQ, self.browse(boq_id)).write(vals)
        
        for boq, body in messages_to_post:
            boq.message_post(body=body)

    def write(self, vals):
        if self.env.context.get('revision_copy'):
            return super(ConstructionBOQ, self).write(vals)
        
        ignore_fields = [
            'message_follower_ids', 'state', 'approval_date', 'approved_by', 
            'active', 'total_budget', 'previous_boq_id', 'revision_ids', 
            'display_revision_ids', 'write_date', 'write_uid', 'name',
            'quotation_template_id' # Don't version just for changing the dropdown
        ]
        
        has_business_changes = any(f not in ignore_fields for f in vals)
        if has_business_changes:
            boqs_to_revise = self.filtered(
                lambda b: b.state in ['submitted', 'approved', 'locked']
            )
            if boqs_to_revise:
                boqs_to_revise.create_revision_snapshot()
        return super(ConstructionBOQ, self).write(vals)

    # -------------------------------------------------------------------------
    # CONSTRAINTS
    # -------------------------------------------------------------------------
    @api.constrains('state')
    def _check_boq_before_approval(self):
        boqs_to_check = self.filtered(lambda b: b.state == 'approved')
        if not boqs_to_check:
            return
            
        boqs_without_lines = boqs_to_check.filtered(lambda b: not b.boq_line_ids)
        if boqs_without_lines:
            raise ValidationError(_('BOQ cannot be approved without BOQ lines.'))

    @api.constrains('project_id', 'version', 'active')
    def _check_unique_active_version(self):
        active_boqs = self.filtered('active')
        if not active_boqs:
            return
            
        project_version_pairs = [
            (boq.project_id.id, boq.version)
            for boq in active_boqs
        ]
        
        for project_id, version in project_version_pairs:
            duplicate_count = self.search_count([
                ('project_id', '=', project_id),
                ('version', '=', version),
                ('active', '=', True),
                ('id', 'in', active_boqs.ids)
            ])
            if duplicate_count > 1:
                raise ValidationError(_('An active BOQ with this version already exists for this project.'))

    def _check_one_active_boq(self):
        if not self:
            return
            
        project_ids = self.mapped('project_id').ids
        if not project_ids:
            return
            
        existing_boqs = self.search([
            ('project_id', 'in', project_ids),
            ('state', 'in', ['approved', 'locked']),
            ('id', 'not in', self.ids),
            ('active', '=', True)
        ])
        
        if existing_boqs:
            project_names = existing_boqs.mapped('project_id.name')
            raise ValidationError(
                _('There is already an active (Approved or Locked) BOQ for project(s): %s. Please revise the existing one.') % 
                ', '.join(project_names)
            )

class ConstructionBOQLine(models.Model):
    _name = 'construction.boq.line'
    _description = 'BOQ Line Item'
    _order = 'sequence, id'
    
    _inherit = ['analytic.mixin'] 

    # Basic Information
    boq_id = fields.Many2one('construction.boq', string='BOQ Reference', required=True, ondelete='cascade', index=True)
    
    # [FIX] Added project_id related field to handle domains in sub-views where 'parent' is not available
    project_id = fields.Many2one('project.project', related='boq_id.project_id', store=True, readonly=True)
    
    display_type = fields.Selection([
        ('line_section', 'Section'),
        ('line_note', 'Note')
    ], default=False, help="Technical field for UX purpose.")
    
    section_id = fields.Many2one('construction.boq.section', string='Section')

    # Product Information
    product_id = fields.Many2one('product.product', string='Product', 
        domain="[('company_id', 'in', (company_id, False))]")
    
    name = fields.Char(string='Description', required=True)
    
    quantity = fields.Float(string='Budget Qty', default=1.0)
    estimated_rate = fields.Monetary(string='Budget Rate', currency_field='currency_id', default=0.0)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure')
    
    budget_amount = fields.Monetary(string='Budget Amount', compute='_compute_budget_amount', currency_field='currency_id', store=True)
    remaining_amount = fields.Monetary(string='Available Budget', compute='_compute_consumption', currency_field='currency_id', store=True)
    
    # Technical Fields
    description = fields.Text(string='Long Description')
    cost_type = fields.Selection([
        ('material', 'Material'),
        ('labor', 'Labor'),
        ('subcontract', 'Subcontract'),
        ('service', 'Service'),
        ('overhead', 'Overhead')
    ], string='Cost Type', default='material', help="Classifies the type of cost for reporting and analysis.")
    
    # [FIX] Updated domain to use local project_id instead of parent.project_id
    task_id = fields.Many2one('project.task', string='Task', domain="[('project_id', '=', project_id)]")
    activity_code = fields.Char(string='Activity Code', help="Code used to link this BOQ line to a specific project task or schedule activity.")
    
    company_id = fields.Many2one('res.company', related='boq_id.company_id', string='Company', store=True, readonly=True)
    
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', string='Currency', readonly=True, store=True)
    
    sequence = fields.Integer(string='Sequence', default=10)
    
    # Accounting Fields
    expense_account_id = fields.Many2one('account.account', string='Expense Account', check_company=True)
    analytic_account_id = fields.Many2one('account.analytic.account', related='boq_id.analytic_account_id', string='Analytic Account', store=True)
    
    analytic_distribution = fields.Json(string='Analytic Distribution', help="Distribute costs across multiple analytic accounts.")
    
    # Consumption Tracking
    consumed_quantity = fields.Float(string='Consumed Qty', compute='_compute_consumption', store=True)
    consumed_amount = fields.Monetary(string='Consumed Amount', compute='_compute_consumption', currency_field='currency_id', store=True)
    remaining_quantity = fields.Float(string='Remaining Qty', compute='_compute_consumption', store=True)
    
    allow_over_consumption = fields.Boolean(string='Allow Over Consumption', default=False, help="If checked, allows consumption to exceed the budgeted quantity/amount without error.")
    consumption_ids = fields.One2many('construction.boq.consumption', 'boq_line_id', string='Consumptions')
    consumption_percentage = fields.Float(string='Progress', compute='_compute_consumption_percentage', store=False, help="Percentage of budget consumed.")
    
    # Product Configuration Validation
    product_config_valid = fields.Boolean(string='Product Configured', compute='_compute_product_config_valid', store=False)

    # [FIX] New Constraint to ensure data integrity for actual lines vs sections
    @api.constrains('display_type', 'product_id', 'uom_id', 'quantity')
    def _check_line_requirements(self):
        for rec in self:
            if not rec.display_type:
                # If it's a real line (not a section/note)
                if not rec.product_id:
                      raise ValidationError(_('Product is mandatory for BOQ lines that are not Sections/Notes.'))
                if not rec.uom_id:
                      raise ValidationError(_('Unit of Measure is mandatory for BOQ line: %s') % rec.name)
                if rec.quantity <= 0:
                      raise ValidationError(_('Quantity must be positive for BOQ line: %s') % rec.name)

    @api.depends('product_id')
    def _compute_product_config_valid(self):
        for rec in self:
            if not rec.product_id:
                rec.product_config_valid = False
                continue
                
            valid = True
            if not rec.product_id.uom_id:
                valid = False
            if not rec.product_id.standard_price:
                valid = False
            if not rec.product_id.property_account_expense_id and not rec.product_id.categ_id.property_account_expense_categ_id:
                valid = False
                
            rec.product_config_valid = valid

    @api.depends('quantity', 'estimated_rate')
    def _compute_budget_amount(self):
        for rec in self:
            rec.budget_amount = rec.quantity * rec.estimated_rate

    @api.depends('quantity', 'budget_amount', 'consumption_ids.quantity', 'consumption_ids.amount')
    def _compute_consumption(self):
        # BOLT: ⚡ Refactored for performance.
        # This method was re-written to reduce Python loops and database queries.
        # The original implementation iterated through the recordset multiple times.
        # This version separates new (in-memory) and existing (database) records
        # to perform a single efficient `read_group` for existing records and
        # a single loop for new records, improving UI responsiveness on large BOQs.

        # Step 1: Initialize all records. Sections/notes are set to zero and skipped.
        for rec in self:
            if rec.display_type:
                rec.consumed_quantity = 0.0
                rec.consumed_amount = 0.0
                rec.remaining_quantity = 0.0
                rec.remaining_amount = 0.0
            else:
                # Default values for real lines
                rec.consumed_quantity = 0.0
                rec.consumed_amount = 0.0
                rec.remaining_quantity = rec.quantity
                rec.remaining_amount = rec.budget_amount

        # Step 2: Efficiently process records that are saved in the database.
        # A single read_group is much faster than iterating and querying one by one.
        existing_records = self.filtered(lambda r: r.id and not r.display_type)
        if existing_records:
            consumption_data = self.env['construction.boq.consumption'].read_group(
                [('boq_line_id', 'in', existing_records.ids)],
                ['boq_line_id', 'quantity', 'amount'],
                ['boq_line_id']
            )
            consumption_map = {
                data['boq_line_id'][0]: {
                    'quantity': data['quantity'],
                    'amount': data['amount']
                } for data in consumption_data
            }

            for rec in existing_records:
                consumed = consumption_map.get(rec.id)
                if consumed:
                    c_qty = consumed.get('quantity', 0.0)
                    c_amt = consumed.get('amount', 0.0)
                    rec.consumed_quantity = c_qty
                    rec.consumed_amount = c_amt
                    rec.remaining_quantity = rec.quantity - c_qty
                    rec.remaining_amount = rec.budget_amount - c_amt

        # Step 3: Process new (in-memory) records that haven't been saved yet.
        # These must be calculated individually as they don't exist for a read_group.
        new_records = self.filtered(lambda r: not r.id and not r.display_type)
        for rec in new_records:
            if rec.consumption_ids:
                c_qty = sum(rec.consumption_ids.mapped('quantity'))
                c_amt = sum(rec.consumption_ids.mapped('amount'))
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
            if account:
                self.expense_account_id = account
            
            # [FIX] Check for missing configurations but allow user to fix them
            warnings = []
            if not self.product_id.uom_id:
                warnings.append(_('Unit of Measure is missing.'))
            if not self.product_id.standard_price:
                warnings.append(_('Standard Price is missing.'))
            if not self.product_id.property_account_expense_id and not self.product_id.categ_id.property_account_expense_categ_id:
                warnings.append(_('Expense Account is missing.'))

            if warnings:
                return {'warning': {'title': _('Product Configuration Warning'), 'message': _('Product "%s" issues:\n%s') % (self.product_id.name, "\n".join(warnings))}}

    # [FIX] Added automatic selection of Analytic Distribution from BOQ Header
    @api.onchange('boq_id', 'product_id')
    def _onchange_setup_analytics(self):
        """
        Automatically populate the Analytic Distribution (JSON) from the BOQ Header's
        Analytic Account if it hasn't been set manually yet.
        """
        for rec in self:
            if rec.boq_id.analytic_account_id and not rec.analytic_distribution:
                # Create the JSON structure expected by analytic.mixin: {'account_id_str': percentage}
                rec.analytic_distribution = {str(rec.boq_id.analytic_account_id.id): 100.0}

    @api.onchange('section_id')
    def _onchange_section_id(self):
        if self.section_id:
            self.name = self.section_id.name

    @api.onchange('task_id')
    def _onchange_task_id(self):
        if self.task_id and self.task_id.activity_code:
            self.activity_code = self.task_id.activity_code

    @api.constrains('product_id', 'expense_account_id')
    def _check_product_configuration(self):
        """
        FIX: Updated to allow fallback to product account if line account is missing.
        """
        for rec in self.filtered(lambda r: r.product_id and r.display_type is False):
            if not rec.product_id.uom_id:
                raise ValidationError(_('Product "%s" is not properly configured. Unit of Measure is missing.') % rec.product_id.name)
            
            # [FIX] Check if account exists on line OR product before raising error
            account = rec.expense_account_id or \
                      rec.product_id.property_account_expense_id or \
                      rec.product_id.categ_id.property_account_expense_categ_id
                      
            if not account:
                raise ValidationError(_('Product "%s" is not properly configured. Expense Account is missing.') % rec.product_id.name)

    def check_consumption(self, qty, amount):
        self.ensure_one()
        # [FIX] Bypass consumption check for sections/notes
        if self.display_type:
            return

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
        # [FIX] Ensure analytic distribution is set on creation if missing
        for vals in vals_list:
            if 'boq_id' in vals and 'analytic_distribution' not in vals:
                boq = self.env['construction.boq'].browse(vals['boq_id'])
                if boq.analytic_account_id:
                    vals['analytic_distribution'] = {str(boq.analytic_account_id.id): 100.0}

        boq_ids = {vals['boq_id'] for vals in vals_list if vals.get('boq_id')}
        if boq_ids and not self.env.context.get('revision_copy'):
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

    def action_open_advanced_view(self):
        self.ensure_one()
        return {
            'name': _('Advanced BOQ Line'),
            'type': 'ir.actions.act_window',
            'res_model': 'construction.boq.line',
            'view_mode': 'form',
            'res_id': self.id,
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'form_view_ref': 'entrpryz_construction_boq.view_construction_boq_line_advanced_form'}
        }

class ConstructionBOQConsumption(models.Model):
    _name = 'construction.boq.consumption'
    _description = 'BOQ Consumption Ledger'
    _order = 'date desc, id desc'
    
    boq_line_id = fields.Many2one('construction.boq.line', string='BOQ Line', required=True, ondelete='restrict', index=True)
    company_id = fields.Many2one('res.company', related='boq_line_id.company_id', string='Company', store=True, readonly=True)
    
    source_model = fields.Char(string='Source Model', required=True)
    source_id = fields.Integer(string='Source ID', required=True)
    
    quantity = fields.Float(string='Quantity Consumed')
    amount = fields.Monetary(string='Amount Consumed', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', related='boq_line_id.currency_id', store=True)
    
    date = fields.Date(string='Date', default=fields.Date.context_today, required=True)
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user)
    
    @api.model_create_multi
    def create(self, vals_list):
        line_ids = {vals['boq_line_id'] for vals in vals_list if vals.get('boq_line_id')}
        lines = self.env['construction.boq.line'].browse(list(line_ids))
        line_map = {line.id: line for line in lines}
        
        for vals in vals_list:
            line_id = vals.get('boq_line_id')
            if line_id and line_id in line_map:
                line = line_map[line_id]
                # [FIX] Do not process consumption for Sections
                if line.display_type:
                      raise ValidationError(_("Cannot record consumption on a Section/Note BOQ line."))

                qty = vals.get('quantity', 0.0)
                amt = vals.get('amount', 0.0)
                if qty > 0 or amt > 0:
                    line.check_consumption(qty, amt)
        return super(ConstructionBOQConsumption, self).create(vals_list)
    
    def init(self):
        self.env.cr.execute("""
            REVOKE UPDATE, DELETE ON construction_boq_consumption FROM PUBLIC;
        """)