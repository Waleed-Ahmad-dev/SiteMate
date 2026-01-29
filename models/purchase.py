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
    # This fixes the "Invalid composed field" error in the view
    boq_product_ids = fields.Many2many(
        'product.product', 
        compute='_compute_boq_product_ids', 
        string="Allowed BOQ Products"
    )

    @api.depends('boq_id.boq_line_ids.product_id')
    def _compute_boq_product_ids(self):
        for rec in self:
            if rec.boq_id:
                # Get all products linked to the valid BOQ lines (ignoring sections)
                rec.boq_product_ids = rec.boq_id.boq_line_ids.filtered(lambda l: not l.display_type).product_id
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

    @api.constrains('product_qty', 'boq_line_id', 'order_id')
    def _check_boq_limit(self):
        """Optimized constraint method with bulk operations"""
        
        # Separate lines by purchase type and state for efficient processing
        boq_lines = self.filtered(
            lambda l: l.order_id.purchase_type == 'boq' and 
                      l.state in ('draft', 'sent') and 
                      l.boq_line_id
        )
        
        normal_lines = self.filtered(
            lambda l: l.order_id.purchase_type == 'boq' and 
                      not l.boq_line_id
        )
        
        # Check for lines without BOQ in BOQ purchase mode
        if normal_lines:
            raise ValidationError(
                _('For BOQ Purchases, every line must be linked to a BOQ Item.')
            )
        
        # Bulk fetch all related BOQ lines with their data
        if boq_lines:
            boq_line_ids = boq_lines.mapped('boq_line_id.id')
            
            # search_read cannot traverse relations in the fields list.
            # We must use 'project_id' directly, as it exists on the line model (as a related field).
            boq_data = self.env['construction.boq.line'].search_read(
                [('id', 'in', boq_line_ids)],
                ['id', 'remaining_quantity', 'allow_over_consumption', 
                 'name', 'boq_id', 'project_id'] 
            )
            
            # Create lookup dictionaries for O(1) access
            boq_by_id = {data['id']: data for data in boq_data}
            
            # Group lines by boq_line_id for efficient processing
            lines_by_boq = defaultdict(list)
            for line in boq_lines:
                lines_by_boq[line.boq_line_id.id].append(line)
            
            # Check project alignment and quantity limits
            for boq_line_id, lines in lines_by_boq.items():
                boq_info = boq_by_id.get(boq_line_id)
                if not boq_info:
                    continue
                
                # Check project alignment for all lines at once
                # Note: boq_info['project_id'] returns (ID, Name) tuple in search_read
                project_mismatch_lines = [
                    line for line in lines 
                    if (line.order_id.project_id and 
                        boq_info['project_id'] and 
                        boq_info['project_id'][0] != line.order_id.project_id.id)
                ]
                
                if project_mismatch_lines:
                    raise ValidationError(
                        _('The BOQ Line selected does not belong to the Project on the Purchase Order.')
                    )
                
                # Check quantity limits for lines where over-consumption is not allowed
                if not boq_info['allow_over_consumption']:
                    remaining_qty = boq_info['remaining_quantity']
                    
                    # Calculate total quantity being purchased in this order for this specific BOQ line
                    total_purchase_qty = sum(line.product_qty for line in lines)
                    
                    if total_purchase_qty > remaining_qty:
                        raise ValidationError(
                            _('Total Purchase Quantity (%s) exceeds BOQ Remaining Quantity (%s) for item %s.') % (
                                total_purchase_qty,
                                remaining_qty,
                                boq_info['name']
                            )
                        )