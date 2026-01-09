from odoo.tests.common import TransactionCase

class TestBOQReportSecurity(TransactionCase):

    def test_report_company_security(self):
        """ Verify that construction.boq.report has company_id field and multi-company rule. """

        # 1. Check if company_id field exists in the model
        model = self.env['construction.boq.report']
        self.assertIn('company_id', model.fields_get(), "construction.boq.report missing company_id field for multi-company security")

        # 2. Check if there is a record rule for it
        # We look for a rule that applies to this model and restricts by company_id
        rules = self.env['ir.rule'].search([('model_id.model', '=', 'construction.boq.report')])
        self.assertTrue(rules, "No record rules found for construction.boq.report")

        # Check if any rule enforces company_id check
        found_security_rule = False
        for rule in rules:
            if 'company_id' in rule.domain_force:
                found_security_rule = True
                break

        self.assertTrue(found_security_rule, "No multi-company security rule found for construction.boq.report")
