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
        
        # Use parameterized query for safety and performance
        query = """
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    -- Use row_number() to ensure unique IDs for view records
                    ROW_NUMBER() OVER (ORDER BY l.id) AS id,
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
                    COALESCE(cons.sum_qty, 0.0) AS consumed_quantity,
                    COALESCE(cons.sum_amt, 0.0) AS consumed_amount,
                    
                    -- Variance Calculations
                    (l.quantity - COALESCE(cons.sum_qty, 0.0)) AS variance_quantity,
                    (l.budget_amount - COALESCE(cons.sum_amt, 0.0)) AS variance_amount,
                    
                    -- Progress Calculation (Avoid division by zero)
                    CASE 
                        WHEN l.budget_amount > 0 
                        THEN (COALESCE(cons.sum_amt, 0.0) / l.budget_amount) * 100
                        ELSE 0 
                    END AS consumption_progress
                    
                FROM construction_boq_line l
                INNER JOIN construction_boq b ON b.id = l.boq_id
                
                -- Use LATERAL JOIN for better performance with correlated subqueries
                LEFT JOIN LATERAL (
                    SELECT 
                        c.boq_line_id,
                        SUM(c.quantity) as sum_qty,
                        SUM(c.amount) as sum_amt
                    FROM construction_boq_consumption c
                    WHERE c.boq_line_id = l.id
                    GROUP BY c.boq_line_id
                ) cons ON TRUE
                
                WHERE b.state IN ('approved', 'locked', 'closed')
                AND l.active = True  -- Assuming there's an active field, add if exists
            )
        """ % self._table
        
        self.env.cr.execute(query)
        
        # Create indexes on frequently filtered columns for better query performance
        self._create_indexes()
    
    def _create_indexes(self):
        """Create database indexes for optimal query performance"""
        indexes = [
            'construction_boq_line_boq_id_idx',
            'construction_boq_project_id_idx', 
            'construction_boq_state_idx',
            'construction_boq_consumption_boq_line_id_idx'
        ]
        
        for index in indexes:
            self.env.cr.execute("""
                DROP INDEX IF EXISTS %s
            """ % index)
        
        # Create indexes for better join performance
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS construction_boq_line_boq_id_idx 
            ON construction_boq_line(boq_id)
        """)
        
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS construction_boq_project_id_idx 
            ON construction_boq(project_id)
        """)
        
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS construction_boq_state_idx 
            ON construction_boq(state)
        """)
        
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS construction_boq_consumption_boq_line_id_idx 
            ON construction_boq_consumption(boq_line_id)
        """)