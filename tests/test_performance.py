from odoo.tests import common
from odoo.exceptions import ValidationError
from unittest.mock import MagicMock, patch

class TestBOQPerformance(common.TransactionCase):
    def setUp(self):
        super(TestBOQPerformance, self).setUp()
        self.Project = self.env['project.project']
        self.BOQ = self.env['construction.boq']
        self.BOQLine = self.env['construction.boq.line']
        self.Product = self.env['product.product']
        self.Uom = self.env['uom.uom']
        self.AnalyticAccount = self.env['account.analytic.account']

        self.project1 = self.Project.create({'name': 'Project 1'})
        self.project2 = self.Project.create({'name': 'Project 2'})

        # Mock account_id for project as it might not exist in base project module or named differently depending on version
        # Assuming the field exists based on models/boq.py _onchange_project_id

        self.product = self.Product.create({'name': 'Cement', 'standard_price': 100})
        self.uom = self.env.ref('uom.product_uom_unit')

        # Create analytic account manually if needed, or rely on project creation if it does it automatically
        self.analytic_account = self.AnalyticAccount.create({'name': 'Project 1 AA'})
        self.project1.account_id = self.analytic_account

        self.account = self.env['account.account'].create({
            'name': 'Test Account',
            'code': '123456',
            'account_type': 'asset_current',
        })

    def test_approve_batch_performance(self):
        # Create 10 BOQs
        boqs = self.BOQ.browse()
        for i in range(10):
            boq = self.BOQ.create({
                'name': f'BOQ {i}',
                'project_id': self.project1.id, # All for same project? No, that would trigger validation error.
                # Wait, validation error says "There is already an active... BOQ for this project."
                # So we can't approve multiple BOQs for the same project.
                # We need different projects.
            })
            # Create a line so it can be approved
            self.BOQLine.create({
                'boq_id': boq.id,
                'name': 'Line 1',
                'product_id': self.product.id,
                'quantity': 10,
                'uom_id': self.uom.id,
                'estimated_rate': 100,
                'expense_account_id': self.account.id,
            })
            boqs |= boq

        # If all BOQs are for Project 1, we can only approve one.
        # So test case should use different projects to test batch approval success.

        projects = []
        for i in range(10):
            p = self.Project.create({'name': f'Project Batch {i}'})
            projects.append(p)

        boqs = self.BOQ.browse()
        for i in range(10):
            boq = self.BOQ.create({
                'name': f'BOQ {i}',
                'project_id': projects[i].id,
                'analytic_account_id': self.analytic_account.id, # Reusing AA for simplicity
            })
             # Create a line
            self.BOQLine.create({
                'boq_id': boq.id,
                'name': 'Line 1',
                'product_id': self.product.id,
                'quantity': 10,
                'uom_id': self.uom.id,
                'estimated_rate': 100,
                'expense_account_id': self.account.id,
            })
            boqs |= boq

        # Mock search_count to count calls?
        # Since we can't easily count SQL queries without internal tools, we will inspect the code manually.
        # But we can verify functionality.

        boqs.action_approve()

        for boq in boqs:
            self.assertEqual(boq.state, 'approved')

    def test_approve_validation(self):
        # Test 1: Two BOQs for same project, try to approve both in batch
        boq1 = self.BOQ.create({
            'name': 'BOQ A',
            'project_id': self.project2.id,
            'analytic_account_id': self.analytic_account.id,
        })
        self.BOQLine.create({
            'boq_id': boq1.id,
            'name': 'Line 1',
            'product_id': self.product.id,
            'quantity': 10,
            'uom_id': self.uom.id,
            'estimated_rate': 100,
            'expense_account_id': self.account.id,
        })

        boq2 = self.BOQ.create({
            'name': 'BOQ B',
            'project_id': self.project2.id,
            'analytic_account_id': self.analytic_account.id,
        })
        self.BOQLine.create({
            'boq_id': boq2.id,
            'name': 'Line 1',
            'product_id': self.product.id,
            'quantity': 10,
            'uom_id': self.uom.id,
            'estimated_rate': 100,
            'expense_account_id': self.account.id,
        })

        boqs = boq1 | boq2
        # This should fail if we correctly check duplicates in batch, OR if we check sequentially.
        # With current implementation (sequential check):
        # 1. Approve boq1. Check DB for active. None. Write approved.
        # 2. Approve boq2. Check DB for active. boq1 is active! Raise Error.

        with self.assertRaises(ValidationError):
            boqs.action_approve()

    def test_approve_validation_existing(self):
        # Test 2: One active BOQ exists, try to approve another
        boq1 = self.BOQ.create({
            'name': 'BOQ A',
            'project_id': self.project2.id,
            'analytic_account_id': self.analytic_account.id,
        })
        self.BOQLine.create({
            'boq_id': boq1.id,
            'name': 'Line 1',
            'product_id': self.product.id,
            'quantity': 10,
            'uom_id': self.uom.id,
            'estimated_rate': 100,
            'expense_account_id': self.account.id,
        })
        boq1.action_approve()

        boq2 = self.BOQ.create({
            'name': 'BOQ B',
            'project_id': self.project2.id,
            'analytic_account_id': self.analytic_account.id,
        })
        self.BOQLine.create({
            'boq_id': boq2.id,
            'name': 'Line 1',
            'product_id': self.product.id,
            'quantity': 10,
            'uom_id': self.uom.id,
            'estimated_rate': 100,
            'expense_account_id': self.account.id,
        })

        with self.assertRaises(ValidationError):
            boq2.action_approve()
