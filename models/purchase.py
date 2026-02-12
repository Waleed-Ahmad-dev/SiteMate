# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, Command
from odoo.exceptions import ValidationError
from collections import defaultdict

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    # Task 8.1: Add purchase mode and BOQ selection
    purchase_type = fields.Selection([
        ('normal', 'Normal Purchase'),
        ('boq', 'BOQ Purchase')
    ], string='Purchase Mode', default='normal', required=True,
       help="Select 'BOQ Purchase' to enforce budget controls.")

    project_id = fields.Many2one('project.project', string='Project')
    
    boq_id = fields.Many2one(
        'construction.boq', 
        string='BOQ Reference', 
        domain="[('project_id', '=', project_id), ('state', 'in', ('approved', 'locked'))]"
    )

    # [FIX] New Computed Field to allow Domain filtering in XML
    boq_product_ids = fields.Many2many(
        'product.product', 
        compute='_compute_boq_product_ids', 
        string="Allowed BOQ Products"
    )

    # Task 2.2: Filter Products by BOQ Availability
    @api.depends('boq_id.boq_line_ids.product_id', 'boq_id.boq_line_ids.is_complete')
    def _compute_boq_product_ids(self):
        for rec in self:
            if rec.boq_id:
                # Filter out BOQ lines that are sections OR are already complete
                rec.boq_product_ids = rec.boq_id.boq_line_ids.filtered(
                    lambda l: not l.display_type and not l.is_complete
                ).product_id
            else:
                rec.boq_product_ids = False

    @api.onchange('purchase_type')
    def _onchange_purchase_type(self):
        """Clear fields if switching back to normal"""
        if self.purchase_type == 'normal':
            self.project_id = False
            self.boq_id = False
            # Optional: Clear lines if switching modes to prevent data inconsistency
            self.order_line = [Command.clear()]

    @api.onchange('boq_id')
    def _onchange_boq_id_clean_lines(self):
        """
        When a BOQ is selected, we DO NOT populate lines automatically.
        We only clear existing lines to ensure the user starts fresh and manually
        selects only what they need to buy.
        """
        if not self.boq_id or self.purchase_type != 'boq':
            return

        # 1. Clear existing lines to prevent duplicates or mix-ups
        self.order_line = [Command.clear()]

    @api.constrains('project_id', 'boq_id', 'purchase_type')
    def _check_boq_project_match(self):
        for order in self:
            if order.purchase_type == 'boq' and order.project_id and order.boq_id:
                if order.boq_id.project_id != order.project_id:
                    raise ValidationError(_("The selected BOQ does not belong to the selected Project."))

    # -------------------------------------------------------------------------
    # Phase 3: Automation & Versioning
    # -------------------------------------------------------------------------
    def button_confirm(self):
        """
        Task 3.1: Trigger Versioning on PO Confirmation.
        Automatically version the BOQ when a Purchase Order is confirmed 
        to snapshot the state at that moment.
        """
        for order in self:
            if order.purchase_type == 'boq' and order.boq_id:
                # Create a revision snapshot of the BOQ *before* the PO is confirmed.
                # This ensures we have a history of the BOQ state prior to this commitment.
                order.boq_id.create_revision_snapshot()

        # Task 3.2: Auto-Update BOQ Status
        # Calling super() changes the PO line states to 'purchase'.
        # This automatically triggers the compute dependency on construction.boq.line:
        #   ordered_quantity (depends on purchase_line_ids.state)
        #   -> remaining_quantity
        #   -> is_complete
        res = super(PurchaseOrder, self).button_confirm()
        return res


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    # Task 8.3: Update boq_line_id domain to filter by the specific Header BOQ
    boq_line_id = fields.Many2one(
        'construction.boq.line',
        string='BOQ Item',
        index=True,
        # Domain filters items belonging to the selected BOQ in the Header
        domain="[('boq_id', '=', parent.boq_id), ('boq_id.state', 'in', ('approved', 'locked')), ('display_type', '=', False)]"
    )

    # -------------------------------------------------------------------------
    # [NEW] PREPARE INVOICE LINE (Replaces AccountMoveLine.create override)
    # -------------------------------------------------------------------------
    def _prepare_account_move_line(self, move=False):
        """
        Prepare the dict of values to create the new account.move.line record.
        This ensures BOQ data flows to the Vendor Bill automatically.
        """
        res = super(PurchaseOrderLine, self)._prepare_account_move_line(move)
        
        # Propagate BOQ Line ID
        if self.boq_line_id:
            res['boq_line_id'] = self.boq_line_id.id
            
            # Propagate Analytics if not already set by standard Odoo flow
            if self.boq_line_id.analytic_distribution and not res.get('analytic_distribution'):
                res['analytic_distribution'] = self.boq_line_id.analytic_distribution
                
        return res

    # -------------------------------------------------------------------------
    # NEW LOGIC: Auto-select BOQ Line when Product is selected
    # -------------------------------------------------------------------------
    @api.onchange('product_id')
    def _onchange_product_id_auto_select_boq(self):
        """
        When a Product is selected, automatically find the matching BOQ Line 
        from the BOQ selected in the Purchase Order Header.
        """
        if not self.product_id or self.order_id.purchase_type != 'boq' or not self.order_id.boq_id:
            return

        # Prevent loop if the BOQ line is already set and matches the product
        if self.boq_line_id and self.boq_line_id.product_id == self.product_id:
            return

        # Search for the BOQ line in the header's BOQ that matches this product
        matching_boq_line = self.env['construction.boq.line'].search([
            ('boq_id', '=', self.order_id.boq_id.id),
            ('product_id', '=', self.product_id.id),
            ('display_type', '=', False)
        ], limit=1)

        if matching_boq_line:
            self.boq_line_id = matching_boq_line.id
            # Manually trigger the BOQ Line onchange to pull description, rates, analytics
            self._onchange_boq_line_id()
        else:
            # If product is not in BOQ, warn the user (Optional)
            return {'warning': {
                'title': _("Product Not in BOQ"),
                'message': _("The selected product is not part of the selected BOQ.")
            }}

    # -------------------------------------------------------------------------
    # Existing Logic: Auto-fill Product when BOQ Line is selected
    # -------------------------------------------------------------------------
    @api.onchange('boq_line_id')
    def _onchange_boq_line_id(self):
        if not self.boq_line_id:
            return

        # Guard Clause: If a Section or Note is somehow selected, do nothing
        if self.boq_line_id.display_type:
            return

        # 1. Set Product (Only if different, to avoid recursion loop)
        if self.boq_line_id.product_id and self.product_id != self.boq_line_id.product_id:
            self.product_id = self.boq_line_id.product_id

        # 2. Map explicit BOQ data (FORCE OVERWRITE)
        self.name = self.boq_line_id.name  # Description from BOQ
        self.product_uom = self.boq_line_id.uom_id  # UoM from BOQ
        self.price_unit = self.boq_line_id.estimated_rate  # Price from BOQ
        
        # 3. Analytics
        if self.boq_line_id.analytic_distribution:
            self.analytic_distribution = self.boq_line_id.analytic_distribution

    # Task 2.1: Enhance PO Line Constraints
    @api.constrains('product_qty', 'boq_line_id', 'order_id')
    def _check_boq_limit(self):
        """
        Phase 2 Gatekeeper: Enforce strict purchasing limits.
        Formula: If (Total Ordered Quantity) > (BOQ Budget + Additional), Raise Error.
        """
        
        # 1. Validation: Ensure all lines in BOQ mode have a BOQ Link
        normal_lines = self.filtered(
            lambda l: l.order_id.purchase_type == 'boq' and \
                      not l.boq_line_id and \
                      l.state != 'cancel'
        )
        if normal_lines:
            raise ValidationError(
                _('For BOQ Purchases, every line must be linked to a BOQ Item.')
            )

        # 2. Filter lines that require Limit Check
        # We check lines that are BOQ Purchase, have a BOQ Line, Over-Consumption NOT allowed, and NOT cancelled.
        lines_to_check = self.filtered(
            lambda l: l.order_id.purchase_type == 'boq' and \
                      l.boq_line_id and \
                      not l.boq_line_id.allow_over_consumption and \
                      l.state != 'cancel'
        )
        
        if not lines_to_check:
            return

        # 3. Group by BOQ Line to perform efficient bulk validation
        # This handles cases where a user might add multiple lines for the same BOQ item in one order.
        boq_line_ids = lines_to_check.mapped('boq_line_id')
        
        for boq_line in boq_line_ids:
            # A. Calculate the Hard Limit
            limit_qty = boq_line.quantity + boq_line.additional_quantity
            
            # B. Calculate Total Ordered Quantity (The "Consumed" part of the budget)
            # We explicitly sum ALL non-cancelled PO lines in the system linked to this BOQ item.
            # This includes the lines currently being saved (self), as constrains run after DB write.
            domain = [
                ('boq_line_id', '=', boq_line.id),
                ('state', '!=', 'cancel')
            ]
            
            # efficient read_group to sum 'product_qty'
            result = self.env['purchase.order.line'].read_group(
                domain, ['product_qty'], ['boq_line_id']
            )
            total_ordered = result[0]['product_qty'] if result else 0.0
            
            # C. The Gatekeeper Check
            # Use 0.0001 epsilon for floating point safety
            if total_ordered > (limit_qty + 0.0001):
                raise ValidationError(
                    _('Purchasing Limit Exceeded for BOQ Item "%(name)s".\n'
                      '------------------------------------------------\n'
                      'Budget Qty: %(budget)s\n'
                      'Additional Qty: %(additional)s\n'
                      'Total Limit: %(limit)s\n'
                      'Total Ordered (incl. this PO): %(ordered)s') % {
                        'name': boq_line.name,
                        'budget': boq_line.quantity,
                        'additional': boq_line.additional_quantity,
                        'limit': limit_qty,
                        'ordered': total_ordered
                    }
                )