# models/stock.py
# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class StockMove(models.Model):
    _inherit = 'stock.move'

    [cite_start]# [cite: 75] Link this move to a BOQ line for budget tracking.
    boq_line_id = fields.Many2one(
        'construction.boq.line',
        string='BOQ Line',
        index=True,
        domain="[('boq_id.state', 'in', ('approved', 'locked'))]",
        help="Link this move to a BOQ line for budget tracking."
    )

    # ---------------------------------------------------------
    # Constraints & Validations
    # ---------------------------------------------------------

    @api.constrains('boq_line_id', 'product_id')
    def _check_boq_product_match(self):
        """
        [cite_start][cite: 75] Verify stock move product matches the BOQ line product.
        """
        for move in self:
            if move.boq_line_id and move.boq_line_id.product_id != move.product_id:
                raise ValidationError(_(
                    "The product in the stock move (%s) must match the BOQ line product (%s)."
                ) % (move.product_id.name, move.boq_line_id.product_id.name))

    # ---------------------------------------------------------
    # Subtask 1.2: Override Accounting Valuation
    # ---------------------------------------------------------

    def _get_dest_account(self, accounts_data):
        """
        Override the destination account for stock valuation.
        [cite_start][cite: 77] Valuation posted to BOQ expense account.
        
        If this move is linked to a BOQ Line and is being issued out (Customer/Production),
        we override the default Category Expense Account with the BOQ Line's Expense Account.
        """
        # Standard Odoo/Cybrosys logic to get the default account
        destination_account_id = super(StockMove, self)._get_dest_account(accounts_data)

        # Custom Logic: If BOQ Line exists, use its expense account
        if self.boq_line_id and self.location_dest_id.usage in ('customer', 'production'):
            if not self.boq_line_id.expense_account_id:
                raise ValidationError(_("The linked BOQ Line %s has no Expense Account configured.") % self.boq_line_id.name)
            return self.boq_line_id.expense_account_id.id
            
        return destination_account_id

    # ---------------------------------------------------------
    # Subtask 1.1: Consumption Recording & Validation
    # ---------------------------------------------------------

    def _action_done(self, cancel_backorder=False):
        """
        Override _action_done to:
        1. [cite_start]Enforce BOQ limits (Validation) [cite: 162]
        2. [cite_start]Create Consumption Ledger entries (Recording) [cite: 75, 76]
        """
        # 1. PRE-VALIDATION PHASE (Before move is Done)
        for move in self:
            # Only process if linked to BOQ and issuing out (not incoming vendors/returns)
            if move.boq_line_id and move.state != 'done' and move.location_dest_id.usage in ('customer', 'production'):
                
                # Get quantity being processed
                qty_to_process = move.quantity
                
                if qty_to_process <= 0:
                    continue

                [cite_start]# [cite: 76, 162] Check BOQ Limit
                if not move.boq_line_id.allow_over_consumption:
                    # Compare against remaining quantity
                    if qty_to_process > move.boq_line_id.remaining_quantity:
                        raise ValidationError(
                            _('Cannot process stock move for %s.\nIssued Quantity (%s) exceeds BOQ Remaining Quantity (%s).') % (
                                move.product_id.name,
                                qty_to_process,
                                move.boq_line_id.remaining_quantity
                            )
                        )

        # 2. CALL SUPER (Perform the Stock Move)
        res = super(StockMove, self)._action_done(cancel_backorder=cancel_backorder)

        # 3. POST-PROCESSING PHASE (Create Consumption Ledger)
        Consumption = self.env['construction.boq.consumption']

        for move in self:
            if move.state == 'done' and move.boq_line_id:
                
                # Only record consumption if items are leaving the company (to Site/Customer)
                # We ignore Internal Transfers or Vendor Receipts here
                if move.location_dest_id.usage in ('customer', 'production'):
                    
                    # Calculate Amount (Quantity * Cost)
                    # Note: We use the value from the stock move if available, otherwise estimate
                    price_unit = abs(move.price_unit) # Standard Cost / Moving Average Cost
                    amount_consumed = price_unit * move.quantity

                    [cite_start]# [cite: 75] Create Consumption Entry
                    Consumption.create({
                        'boq_line_id': move.boq_line_id.id,
                        'source_model': 'stock.move',
                        'source_id': move.id,
                        'quantity': move.quantity,
                        'amount': amount_consumed, # Use stock valuation cost
                        'date': move.date or fields.Date.today(),
                        'user_id': self.env.user.id
                    })

                    # Optional: Explicit check updates on the BOQ line for real-time validation
                    # (Though the constraint above handles the "Before" check)
                    move.boq_line_id.check_consumption(0, 0) # Trigger checks/recomputes if needed

        return res