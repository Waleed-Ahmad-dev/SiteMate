# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class AccountMove(models.Model):
    _inherit = 'account.move'

    # Step 3.1 & 3.2: Implement Ledger Writing & Concurrency Locking
    def action_post(self):
        """
        Override action_post to Create BOQ Consumption Ledger entries.
        Includes Concurrency Locking (Step 3.2).
        """
        # 1. Identify moves that need BOQ processing (Vendor Bills/Refunds)
        moves_to_process = self.filtered(lambda m: m.is_invoice(include_receipts=True))
        
        Consumption = self.env['construction.boq.consumption']
        
        for move in moves_to_process:
            # Determine direction: Refund reduces consumption, Invoice increases it
            sign = -1 if move.move_type in ('in_refund', 'out_refund') else 1

            for line in move.invoice_line_ids:
                if line.boq_line_id:
                    # Step 3.2: Implement Concurrency Locking
                    # TDD Section 10.4: Use SELECT FOR UPDATE to prevent race conditions.
                    # We do NOT use NOWAIT, allowing the transaction to wait nicely if locked.
                    self.env.cr.execute(
                        "SELECT id FROM construction_boq_line WHERE id=%s FOR UPDATE",
                        (line.boq_line_id.id,)
                    )
                    
                    # Prepare values
                    # Convert quantity based on move type
                    qty_to_consume = line.quantity * sign
                    
                    # Handle Currency Conversion for Amount
                    # BOQ is in Company Currency, Bill might be in Foreign Currency
                    amount_currency = line.currency_id
                    amount_boq_currency = line.boq_line_id.currency_id
                    
                    if amount_currency != amount_boq_currency:
                        # Convert line amount to BOQ currency
                        amount_to_consume = amount_currency._convert(
                            line.price_subtotal,
                            amount_boq_currency,
                            move.company_id,
                            move.date or fields.Date.today()
                        ) * sign
                    else:
                        amount_to_consume = line.price_subtotal * sign

                    # Validate Limits
                    # We check positive consumption against remaining budget.
                    # Refunds (negative) are generally allowed as they free up budget.
                    if sign > 0:
                        line.boq_line_id.check_consumption(qty_to_consume, amount_to_consume)

                    # Create Ledger Entry
                    Consumption.create({
                        'boq_line_id': line.boq_line_id.id,
                        'source_model': 'account.move.line',
                        'source_id': line.id,
                        'quantity': qty_to_consume,
                        'amount': amount_to_consume,
                        'date': move.date or fields.Date.today(),
                        'user_id': self.env.user.id
                    })

        # 2. Call super to perform standard posting
        return super(AccountMove, self).action_post()


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # Sub-step: Add field boq_line_id
    boq_line_id = fields.Many2one(
        'construction.boq.line',
        string='BOQ Item',
        index=True,
        domain="[('boq_id.state', 'in', ('approved', 'locked'))]",
        help="Link this invoice line to a BOQ line for cost tracking."
    )

    # Sub-step: Auto-populate boq_line_id from Purchase Order Line
    @api.model_create_multi
    def create(self, vals_list):
        """
        Override create to automatically pull the BOQ Line from the linked Purchase Order Line.
        This ensures that when 'Create Bill' is clicked on a PO, the BOQ reference is preserved.
        """
        for vals in vals_list:
            # If this line is linked to a PO line and no BOQ line is manually set
            if vals.get('purchase_line_id') and not vals.get('boq_line_id'):
                po_line = self.env['purchase.order.line'].browse(vals['purchase_line_id'])
                if po_line.boq_line_id:
                    vals['boq_line_id'] = po_line.boq_line_id.id
                    # [cite_start]Subtask 4.1: Propagate Analytics to Bills (Create) [cite: 16]
                    if po_line.boq_line_id.analytic_distribution and not vals.get('analytic_distribution'):
                        vals['analytic_distribution'] = po_line.boq_line_id.analytic_distribution
        
        return super(AccountMoveLine, self).create(vals_list)

    @api.onchange('purchase_line_id')
    def _onchange_purchase_line_id_boq(self):
        """
        Handle UI updates when a user manually selects a PO line on a Vendor Bill.
        """
        if self.purchase_line_id and self.purchase_line_id.boq_line_id:
            self.boq_line_id = self.purchase_line_id.boq_line_id
            # [cite_start]Subtask 4.1: Propagate Analytics to Bills (OnChange PO) [cite: 16]
            if self.boq_line_id.analytic_distribution:
                self.analytic_distribution = self.boq_line_id.analytic_distribution

    @api.onchange('boq_line_id')
    def _onchange_boq_line_id_analytics(self):
        """
        [cite_start]Subtask 4.1: Propagate Analytics to Bills (OnChange BOQ) [cite: 16]
        Handle UI updates when a user manually selects a BOQ line directly.
        """
        if self.boq_line_id and self.boq_line_id.analytic_distribution:
            self.analytic_distribution = self.boq_line_id.analytic_distribution