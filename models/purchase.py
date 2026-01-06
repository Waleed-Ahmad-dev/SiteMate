# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

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


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    # Task 8.3: Update boq_line_id domain to filter by the specific Header BOQ
    boq_line_id = fields.Many2one(
        'construction.boq.line',
        string='BOQ Item',
        index=True,
        # Dynamic domain: Must belong to the BOQ selected in the header
        domain="[('boq_id', '=', parent.boq_id), ('boq_id.state', 'in', ('approved', 'locked'))]"
    )

    @api.onchange('boq_line_id')
    def _onchange_boq_line_id(self):
        if self.boq_line_id:
            if not self.product_id:
                self.product_id = self.boq_line_id.product_id
            if not self.product_uom:
                self.product_uom = self.boq_line_id.uom_id
            if self.boq_line_id.analytic_distribution:
                self.analytic_distribution = self.boq_line_id.analytic_distribution

    @api.constrains('product_qty', 'boq_line_id', 'order_id')
    def _check_boq_limit(self):
        for line in self:
            # Task 8.3.2: Validate Mode
            if line.order_id.purchase_type == 'boq':
                if not line.boq_line_id:
                    raise ValidationError(_('For BOQ Purchases, every line must be linked to a BOQ Item.'))
                
                # Check Project Alignment
                if line.order_id.project_id and line.boq_line_id.boq_id.project_id != line.order_id.project_id:
                    raise ValidationError(_('The BOQ Line selected does not belong to the Project on the Purchase Order.'))

            # Standard Quantity Checks (Only run if linked to BOQ)
            if line.boq_line_id and line.state in ('draft', 'sent'):
                if not line.boq_line_id.allow_over_consumption:
                    if line.product_qty > line.boq_line_id.remaining_quantity:
                        raise ValidationError(
                            _('Purchase Quantity (%s) exceeds BOQ Remaining Quantity (%s) for item %s.') % (
                                line.product_qty,
                                line.boq_line_id.remaining_quantity,
                                line.boq_line_id.name
                            )
                        )