# -*- coding: utf-8 -*-
from odoo import models, fields, tools

class ConstructionBOQReport(models.Model):
    _name = 'construction.boq.report'
    _description = 'BOQ Budget vs Actual Analysis'
    _auto = False
    _rec_name = 'boq_line_id'
    _order = 'project_id, boq_id'

    # Dimensions
    boq_line_id = fields.Many2one('construction.boq.line', string='BOQ Line', readonly=True)
    boq_id = fields.Many2one('construction.boq', string='BOQ Reference', readonly=True)
    project_id = fields.Many2one('project.project', string='Project', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    cost_type = fields.Selection([
        ('material', 'Material'), 
        ('labor', 'Labor'), 
        ('subcontract', 'Subcontract'), 
        ('service', 'Service'), 
        ('overhead', 'Overhead')
    ], string='Cost Type', readonly=True)
    
    # Measures: Budget
    budget_quantity = fields.Float(string='Budget Qty', readonly=True)
    budget_amount = fields.Monetary(string='Budget Amount', readonly=True)
    
    # Measures: Actuals (Aggregated from Consumption Ledger)
    consumed_quantity = fields.Float(string='Actual Qty', readonly=True)
    consumed_amount = fields.Monetary(string='Actual Amount', readonly=True)
    
    # Measures: Variances (Calculated in SQL)
    variance_quantity = fields.Float(string='Variance Qty', readonly=True, help="Budget Qty - Actual Qty")
    variance_amount = fields.Monetary(string='Variance Amount', readonly=True, help="Budget Amount - Actual Amount")
    
    # Measures: Percentage (Optional utility for graph views)
    consumption_progress = fields.Float(string='Consumption %', readonly=True, group_operator="avg")

    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    -- ID generation for the view
                    l.id AS id,
                    l.id AS boq_line_id,
                    l.boq_id,
                    b.project_id,
                    b.company_id,
                    l.analytic_account_id,
                    l.product_id,
                    l.cost_type,
                    l.currency_id,
                    
                    -- Budget Columns
                    l.quantity AS budget_quantity,
                    l.budget_amount AS budget_amount,
                    
                    -- Actual Columns (Aggregated from Ledger)
                    COALESCE(consumption.qty, 0.0) AS consumed_quantity,
                    COALESCE(consumption.amt, 0.0) AS consumed_amount,
                    
                    -- Variance Calculations
                    (l.quantity - COALESCE(consumption.qty, 0.0)) AS variance_quantity,
                    (l.budget_amount - COALESCE(consumption.amt, 0.0)) AS variance_amount,
                    
                    -- Progress Calculation (Avoid division by zero)
                    CASE 
                        WHEN l.budget_amount > 0 THEN (COALESCE(consumption.amt, 0.0) / l.budget_amount) * 100
                        ELSE 0 
                    END AS consumption_progress
                    
                FROM construction_boq_line l
                JOIN construction_boq b ON b.id = l.boq_id
                
                -- Left Join to aggregate consumption per BOQ Line
                LEFT JOIN (
                    SELECT 
                        boq_line_id, 
                        SUM(quantity) as qty, 
                        SUM(amount) as amt
                    FROM construction_boq_consumption
                    GROUP BY boq_line_id
                ) consumption ON consumption.boq_line_id = l.id
                
                WHERE b.state IN ('approved', 'locked', 'closed')
            )
        """ % self._table)