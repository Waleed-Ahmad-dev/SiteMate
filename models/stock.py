# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class StockMove(models.Model):
    _inherit = 'stock.move'

    # [cite: 75] Link this move to a BOQ line for budget tracking.
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
        Verify stock move product matches the BOQ line product.
        """
        # Use filtered instead of looping to identify invalid records
        invalid_moves = self.filtered(
            lambda m: m.boq_line_id and m.boq_line_id.product_id != m.product_id
        )
        
        if invalid_moves:
            # Raise a single error for all invalid moves
            move_info = [
                _("%s (move product) vs %s (BOQ product)") % 
                (m.product_id.name, m.boq_line_id.product_id.name)
                for m in invalid_moves
            ]
            raise ValidationError(
                _("Product mismatch in stock moves:\n%s") % 
                "\n".join(move_info)
            )

    # ---------------------------------------------------------
    # Subtask 1.2: Override Accounting Valuation
    # ---------------------------------------------------------

    def _get_dest_account(self, accounts_data):
        """
        Override the destination account for stock valuation.
        Valuation posted to BOQ expense account.
        
        If this move is linked to a BOQ Line and is being issued out (Customer/Production),
        we override the default Category Expense Account with the BOQ Line's Expense Account.
        """
        # Standard Odoo/Cybrosys logic to get the default account
        destination_account_id = super()._get_dest_account(accounts_data)

        # Custom Logic: If BOQ Line exists, use its expense account
        if self.boq_line_id and self.location_dest_id.usage in ('customer', 'production'):
            if not self.boq_line_id.expense_account_id:
                raise ValidationError(
                    _("The linked BOQ Line %s has no Expense Account configured.") % 
                    self.boq_line_id.name
                )
            return self.boq_line_id.expense_account_id.id
            
        return destination_account_id

    def _prepare_account_move_line(self, qty, cost, credit_account_id, debit_account_id, description):
        """
        Inject analytic distribution from BOQ Line into the Stock Journal Entry.
        This ensures that when a stock move is posted, the resulting Journal Entry carries 
        the Project/Analytic Account defined in the BOQ.
        """
        self.ensure_one()
        # Call super to get the list of move line values [(0, 0, vals), (0, 0, vals)]
        res = super()._prepare_account_move_line(qty, cost, credit_account_id, debit_account_id, description)
        
        if self.boq_line_id and self.boq_line_id.analytic_distribution:
            # Use list comprehension for more efficient processing
            return [
                (command, cid, dict(vals, **{
                    'analytic_distribution': self.boq_line_id.analytic_distribution
                }) if (
                    len(tuple_data) == 3 and 
                    vals.get('account_id') == debit_account_id
                ) else vals)
                for command, cid, vals in res
            ]
            
        return res

    # ---------------------------------------------------------
    # Subtask 1.1: Consumption Recording & Validation
    # ---------------------------------------------------------

    def _action_done(self, cancel_backorder=False):
        """
        Override _action_done to:
        1. Enforce BOQ limits (Validation)
        2. Create Consumption Ledger entries (Recording)
        """
        # 1. PRE-VALIDATION PHASE (Before move is Done)
        # Pre-filter moves that need validation
        moves_to_validate = self.filtered(
            lambda m: (
                m.boq_line_id and 
                m.state != 'done' and 
                m.location_dest_id.usage in ('customer', 'production') and
                m.quantity > 0
            )
        )
        
        if moves_to_validate:
            # Bulk read remaining quantities to avoid N+1 queries
            boq_line_ids = moves_to_validate.mapped('boq_line_id.id')
            boq_lines = self.env['construction.boq.line'].browse(boq_line_ids)
            
            # Create a dictionary for quick lookup
            remaining_qty_dict = {
                line.id: line.remaining_quantity
                for line in boq_lines
                if not line.allow_over_consumption
            }
            
            # Check all moves in batch
            invalid_moves = []
            for move in moves_to_validate:
                remaining_qty = remaining_qty_dict.get(move.boq_line_id.id)
                if remaining_qty is not None and move.quantity > remaining_qty:
                    invalid_moves.append(move)
            
            if invalid_moves:
                move_info = [
                    _("%s: Issued Quantity (%s) exceeds BOQ Remaining Quantity (%s)") % (
                        m.product_id.name,
                        m.quantity,
                        remaining_qty_dict[m.boq_line_id.id]
                    )
                    for m in invalid_moves
                ]
                raise ValidationError(
                    _('Cannot process stock moves:\n%s') % 
                    "\n".join(move_info)
                )

        # 2. CALL SUPER (Perform the Stock Move)
        res = super()._action_done(cancel_backorder=cancel_backorder)

        # 3. POST-PROCESSING PHASE (Create Consumption Ledger)
        Consumption = self.env['construction.boq.consumption']
        
        # Filter moves that need consumption records
        moves_for_consumption = self.filtered(
            lambda m: (
                m.state == 'done' and 
                m.boq_line_id and 
                m.location_dest_id.usage in ('customer', 'production')
            )
        )
        
        if moves_for_consumption:
            # Prepare all consumption records in batch
            consumption_vals = []
            today = fields.Date.today()
            user_id = self.env.user.id
            
            for move in moves_for_consumption:
                price_unit = abs(move.price_unit)  # Standard Cost / Moving Average Cost
                amount_consumed = price_unit * move.quantity
                
                consumption_vals.append({
                    'boq_line_id': move.boq_line_id.id,
                    'source_model': 'stock.move',
                    'source_id': move.id,
                    'quantity': move.quantity,
                    'amount': amount_consumed,
                    'date': move.date or today,
                    'user_id': user_id
                })
            
            # Create all consumption records in a single database operation
            if consumption_vals:
                Consumption.create(consumption_vals)
                
                # Optional: Group by BOQ line and trigger check_consumption once per line
                boq_line_ids = set(move.boq_line_id.id for move in moves_for_consumption)
                boq_lines = self.env['construction.boq.line'].browse(list(boq_line_ids))
                boq_lines.check_consumption(0, 0)  # Trigger checks/recomputes if needed

        return res