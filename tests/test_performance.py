from odoo.tests.common import TransactionCase

class TestPerformance(TransactionCase):

    def setUp(self):
        super(TestPerformance, self).setUp()
        self.project = self.env['project.project'].create({'name': 'Test Project'})
        self.boq = self.env['construction.boq'].create({
            'name': 'Test BOQ',
            'project_id': self.project.id,
            'state': 'approved'
        })
        self.product = self.env['product.product'].create({
            'name': 'Test Product',
            'standard_price': 100,
        })
        # Create BOQ Line
        self.boq_line = self.env['construction.boq.line'].create({
            'boq_id': self.boq.id,
            'product_id': self.product.id,
            'quantity': 100,
            'estimated_rate': 100,
            'expense_account_id': self.env['account.account'].search([], limit=1).id,
            'uom_id': self.env.ref('uom.product_uom_unit').id,
        })

        # Create some consumptions
        self.env['construction.boq.consumption'].create({
            'boq_line_id': self.boq_line.id,
            'quantity': 10,
            'amount': 1000,
            'source_model': 'stock.move',
            'source_id': 1
        })
        self.env['construction.boq.consumption'].create({
            'boq_line_id': self.boq_line.id,
            'quantity': 20,
            'amount': 2000,
            'source_model': 'stock.move',
            'source_id': 2
        })

    def test_consumption_compute(self):
        """ Verify that splitting the compute method works correctly. """

        # Invalidate cache to force read from DB
        self.boq_line.invalidate_recordset()

        # Read stored fields - should be correct in DB
        self.assertEqual(self.boq_line.consumed_quantity, 30)
        self.assertEqual(self.boq_line.consumed_amount, 3000)

        # Read non-stored field
        # This triggers _compute_consumption_percentage
        # It should NOT trigger _compute_consumption (which computes stored fields)
        # We can't easily assert on function calls here without mocking,
        # but we can verify the result is correct.
        self.assertEqual(self.boq_line.consumption_percentage, 3000 / 10000)

        # Add a new consumption
        self.env['construction.boq.consumption'].create({
            'boq_line_id': self.boq_line.id,
            'quantity': 10,
            'amount': 1000,
            'source_model': 'stock.move',
            'source_id': 3
        })

        # Computed fields should update
        self.assertEqual(self.boq_line.consumed_quantity, 40)
        self.assertEqual(self.boq_line.consumption_percentage, 4000 / 10000)
