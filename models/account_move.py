# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from collections import defaultdict

class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        """
        Override action_post to Create BOQ Consumption Ledger entries.
        Includes Concurrency Locking (Step 3.2).
        """
        # 1. Identify moves that need BOQ processing (Vendor Bills/Refunds)
        moves_to_process = self.filtered(lambda m: m.is_invoice(include_receipts=True))
        
        # Early exit if no moves to process
        if not moves_to_process:
            return super(AccountMove, self).action_post()
        
        Consumption = self.env['construction.boq.consumption']
        
        # Collect all BOQ lines that need to be locked
        boq_lines_to_lock = set()
        lines_with_boq = []
        
        for move in moves_to_process:
            for line in move.invoice_line_ids:
                if line.boq_line_id:
                    boq_lines_to_lock.add(line.boq_line_id.id)
                    lines_with_boq.append((move, line))
        
        # Step 3.2: Implement Concurrency Locking - Lock all BOQ lines at once
        if boq_lines_to_lock:
            self.env.cr.execute(
                """
                SELECT id FROM construction_boq_line
                WHERE id IN %s FOR UPDATE
                """,
                (tuple(boq_lines_to_lock),)
            )
            
            # Bulk invalidate cache for all BOQ lines
            boq_line_ids = list(boq_lines_to_lock)
            boq_lines = self.env['construction.boq.line'].browse(boq_line_ids)
            boq_lines.invalidate_recordset(['id'])
        
        # Group lines by company and currency for batch processing
        consumption_vals_list = []
        
        for move, line in lines_with_boq:
            # Determine direction: Refund reduces consumption, Invoice increases it
            sign = -1 if move.move_type in ('in_refund', 'out_refund') else 1
            
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
            
            # Validate Limits - batch validation would be better but depends on implementation
            # We check positive consumption against remaining budget.
            # Refunds (negative) are generally allowed as they free up budget.
            if sign > 0:
                line.boq_line_id.check_consumption(qty_to_consume, amount_to_consume)
            
            # Prepare consumption entry
            consumption_vals_list.append({
                'boq_line_id': line.boq_line_id.id,
                'source_model': 'account.move.line',
                'source_id': line.id,
                'quantity': qty_to_consume,
                'amount': amount_to_consume,
                'date': move.date or fields.Date.today(),
                'user_id': self.env.user.id
            })
        
        # Create all consumption records in batch
        if consumption_vals_list:
            Consumption.create(consumption_vals_list)
        
        # 2. Call super to perform standard posting
        return super(AccountMove, self).action_post()

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    boq_line_id = fields.Many2one(
        'construction.boq.line',
        string='BOQ Item',
        index=True,
        # [FIX] Added display_type = False to domain
        domain="[('boq_id.state', 'in', ('approved', 'locked')), ('display_type', '=', False)]",
        help="Link this invoice line to a BOQ line for cost tracking."
    )

    @api.model_create_multi
    def create(self, vals_list):
        """
        Override create to automatically pull the BOQ Line from the linked Purchase Order Line.
        This ensures that when 'Create Bill' is clicked on a PO, the BOQ reference is preserved.
        """
        # Collect purchase line IDs that need boq_line_id resolution
        purchase_line_ids = []
        purchase_line_map = {}
        
        for i, vals in enumerate(vals_list):
            if vals.get('purchase_line_id') and not vals.get('boq_line_id'):
                purchase_line_ids.append(vals['purchase_line_id'])
                purchase_line_map[i] = vals['purchase_line_id']
        
        # Bulk fetch purchase order lines with their BOQ lines
        if purchase_line_ids:
            po_lines = self.env['purchase.order.line'].browse(purchase_line_ids)
            
            # FIX APPLIED HERE:
            # We cannot use read() to fetch 'boq_line_id.analytic_distribution' directly from PO Line.
            # Instead, we browse the records and iterate. Odoo's prefetching makes this efficient.
            po_line_info = {}
            for line in po_lines:
                po_line_info[line.id] = {
                    'boq_line_id': line.boq_line_id.id if line.boq_line_id else False,
                    # Access the related field via the object, not via read string
                    'analytic_distribution': line.boq_line_id.analytic_distribution if line.boq_line_id else False
                }
            
            # Apply the BOQ line information
            for i, purchase_line_id in purchase_line_map.items():
                info = po_line_info.get(purchase_line_id)
                if info and info['boq_line_id']:
                    vals_list[i]['boq_line_id'] = info['boq_line_id']
                    # Subtask 4.1: Propagate Analytics to Bills (Create)
                    if info['analytic_distribution'] and not vals_list[i].get('analytic_distribution'):
                        vals_list[i]['analytic_distribution'] = info['analytic_distribution']
        
        return super(AccountMoveLine, self).create(vals_list)

    @api.onchange('purchase_line_id')
    def _onchange_purchase_line_id_boq(self):
        """
        Handle UI updates when a user manually selects a PO line on a Vendor Bill.
        """
        if self.purchase_line_id and self.purchase_line_id.boq_line_id:
            self.boq_line_id = self.purchase_line_id.boq_line_id
            # Subtask 4.1: Propagate Analytics to Bills (OnChange PO)
            if self.boq_line_id.analytic_distribution:
                self.analytic_distribution = self.boq_line_id.analytic_distribution

    @api.onchange('boq_line_id')
    def _onchange_boq_line_id_analytics(self):
        """
        Subtask 4.1: Propagate Analytics to Bills (OnChange BOQ)
        Handle UI updates when a user manually selects a BOQ line directly.
        """
        if self.boq_line_id and self.boq_line_id.analytic_distribution:
            self.analytic_distribution = self.boq_line_id.analytic_distribution