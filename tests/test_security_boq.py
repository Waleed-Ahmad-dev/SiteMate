# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError

class TestBOQSecurity(TransactionCase):
    """
    Test suite to verify security constraints on BOQ Consumption.
    Specifically checks that direct creation of consumption records
    adheres to budget limits, preventing API-based bypasses.
    """

    def setUp(self):
        super(TestBOQSecurity, self).setUp()

        # Setup basic data
        self.project = self.env['project.project'].create({'name': 'Test Project'})
        self.boq = self.env['construction.boq'].create({
            'project_id': self.project.id,
            'name': 'Test BOQ',
            'state': 'approved'
        })

        self.section = self.env['construction.boq.section'].create({'name': 'Test Section'})
        self.product = self.env['product.product'].create({'name': 'Test Product', 'standard_price': 100})
        self.uom = self.env.ref('uom.product_uom_unit')

        self.boq_line = self.env['construction.boq.line'].create({
            'boq_id': self.boq.id,
            'section_id': self.section.id,
            'product_id': self.product.id,
            'quantity': 10.0,
            'estimated_rate': 100.0,
            'uom_id': self.uom.id,
            'cost_type': 'material',
            'expense_account_id': self.env['account.account'].search([], limit=1).id
        })

        # Budget: 10 Qty, 1000 Amount

    def test_direct_consumption_creation_within_limits(self):
        """Test that creating consumption within limits succeeds."""
        consumption = self.env['construction.boq.consumption'].create({
            'boq_line_id': self.boq_line.id,
            'source_model': 'test.model',
            'source_id': 1,
            'quantity': 5.0,
            'amount': 500.0,
        })
        self.assertTrue(consumption)
        self.assertEqual(self.boq_line.consumed_quantity, 5.0)

    def test_direct_consumption_creation_exceeds_limits(self):
        """Test that creating consumption exceeding limits fails."""
        with self.assertRaises(ValidationError, msg="BOQ Quantity Exceeded"):
            self.env['construction.boq.consumption'].create({
                'boq_line_id': self.boq_line.id,
                'source_model': 'test.model',
                'source_id': 2,
                'quantity': 11.0, # Exceeds 10
                'amount': 1100.0,
            })

    def test_incremental_consumption_exceeds_limits(self):
        """Test that incremental consumption respecting total limit works, and exceeding fails."""
        # First consumption (OK)
        self.env['construction.boq.consumption'].create({
            'boq_line_id': self.boq_line.id,
            'source_model': 'test.model',
            'source_id': 3,
            'quantity': 8.0,
            'amount': 800.0,
        })

        # Second consumption (Fail - Total 12 > 10)
        with self.assertRaises(ValidationError):
            self.env['construction.boq.consumption'].create({
                'boq_line_id': self.boq_line.id,
                'source_model': 'test.model',
                'source_id': 4,
                'quantity': 4.0,
                'amount': 400.0,
            })

    def test_negative_consumption_bypass(self):
        """Test that negative consumption (refund) is allowed and increases budget."""
        # Consume all budget
        self.env['construction.boq.consumption'].create({
            'boq_line_id': self.boq_line.id,
            'source_model': 'test.model',
            'source_id': 5,
            'quantity': 10.0,
            'amount': 1000.0,
        })

        # Refund (Negative)
        self.env['construction.boq.consumption'].create({
            'boq_line_id': self.boq_line.id,
            'source_model': 'test.model',
            'source_id': 6,
            'quantity': -2.0,
            'amount': -200.0,
        })

        # Now we have 2 available again. Consume 1. (Should pass)
        self.env['construction.boq.consumption'].create({
            'boq_line_id': self.boq_line.id,
            'source_model': 'test.model',
            'source_id': 7,
            'quantity': 1.0,
            'amount': 100.0,
        })
