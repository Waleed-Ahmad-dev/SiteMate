# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class StockMove(models.Model):
    _inherit = 'stock.move'

    # [cite_start]Sub-step: Add field boq_line_id [cite: 75]
    boq_line_id = fields.Many2one(
        'construction.boq.line', 
        string='BOQ Line', 
        index=True,
        domain="[('boq_id.state', 'in', ('approved', 'locked'))]",
        help="Link this move to a BOQ line for budget tracking."
    )

    # Sub-step: Add validation logic - Product Match
    @api.constrains('boq_line_id', 'product_id')
    def _check_boq_product_match(self):
        for move in self:
            # [cite_start]Verify it matches the BOQ line product [cite: 75]
            if move.boq_line_id and move.boq_line_id.product_id != move.product_id:
                raise ValidationError(_("The product in the stock move (%s) must match the BOQ line product (%s).") % (move.product_id.name, move.boq_line_id.product_id.name))

    # Sub-step: Add validation logic - Quantity Check
    def _action_done(self, cancel_backorder=False):
        """
        Override _action_done to enforce BOQ limits before finalizing the move.
        This covers TDD 10.3 Stock Picking Validation.
        """
        for move in self:
            if move.boq_line_id and move.state != 'done':
                # Check if this is an issue to Internal/Site or general consumption
                # We enforce logic if a BOQ Line is explicitly linked.
                
                # Odoo 17/18 uses 'quantity' for the Done quantity (formerly qty_done or quantity_done)
                qty_to_process = move.quantity
                
                # [cite_start]Check 1: Positive Quantity [cite: 112]
                if qty_to_process <= 0:
                    continue 

                # [cite_start]Check 2: BOQ Limit [cite: 76, 162]
                if not move.boq_line_id.allow_over_consumption:
                    # We compare against remaining quantity.
                    # Note: We do not subtract the current move's qty because 'remaining_quantity' 
                    # is computed from *posted* consumption records, and this move is not yet posted/consumed.
                    if qty_to_process > move.boq_line_id.remaining_quantity:
                        raise ValidationError(
                            _('Cannot process stock move for %s.\nIssued Quantity (%s) exceeds BOQ Remaining Quantity (%s).') % (
                                move.product_id.name,
                                qty_to_process,
                                move.boq_line_id.remaining_quantity
                            )
                        )

        # Proceed with standard Odoo logic
        return super(StockMove, self)._action_done(cancel_backorder=cancel_backorder)