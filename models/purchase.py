# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
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
        domain="[('project_id', '=', project_id), ('state', 'in', ['approved', 'locked'])]"
    )

    @api.onchange('purchase_type')
    def _onchange_purchase_type(self):
        """Clear fields if switching back to normal"""
        if self.purchase_type == 'normal':
            self.project_id = False
            self.boq_id = False

    # [FIX] Scenario 3.1: Constraint on Header to catch Project changes
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
        # [FIX] Added display_type = False to domain
        domain="[('boq_id', '=', parent.boq_id), ('boq_id.state', 'in', ('approved', 'locked')), ('display_type', '=', False)]"
    )

    @api.onchange('boq_line_id')
    def _onchange_boq_line_id(self):
        if not self.boq_line_id:
            return

        # [FIX] Issue 1: Fields weren't populating. 
        # Explicitly map Product, Name, UoM, and Price.
        
        # 1. Set Product 
        # (Setting this might trigger standard Odoo onchanges, but we force values below to be sure)
        if self.boq_line_id.product_id:
            self.product_id = self.boq_line_id.product_id

        # 2. Map explicit BOQ data
        self.name = self.boq_line_id.name  # Description
        self.product_uom = self.boq_line_id.uom_id
        self.price_unit = self.boq_line_id.estimated_rate  # Price
        
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
            
            # Use read_group to fetch remaining quantities in bulk
            boq_data = self.env['construction.boq.line'].search_read(
                [('id', 'in', boq_line_ids)],
                ['id', 'remaining_quantity', 'allow_over_consumption', 
                 'name', 'boq_id', 'boq_id.project_id']
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
                # Note: This checks Line consistency. The Header constraint checks Header consistency.
                project_mismatch_lines = [
                    line for line in lines 
                    if (line.order_id.project_id and 
                        boq_info['boq_id'][0] != line.order_id.project_id.id)
                ]
                
                if project_mismatch_lines:
                    raise ValidationError(
                        _('The BOQ Line selected does not belong to the Project on the Purchase Order.')
                    )
                
                # Check quantity limits for lines where over-consumption is not allowed
                if not boq_info['allow_over_consumption']:
                    remaining_qty = boq_info['remaining_quantity']
                    
                    # Check each line's quantity against the same remaining quantity
                    for line in lines:
                        if line.product_qty > remaining_qty:
                            raise ValidationError(
                                _('Purchase Quantity (%s) exceeds BOQ Remaining Quantity (%s) for item %s.') % (
                                    line.product_qty,
                                    remaining_qty,
                                    boq_info['name']
                                )
                            )