# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class ConstructionBOQRevision(models.Model):
    _name = 'construction.boq.revision'
    _description = 'BOQ Revision History'
    _order = 'create_date desc'

    original_boq_id = fields.Many2one('construction.boq', string='Original BOQ', required=True, readonly=True, ondelete='restrict')
    new_boq_id = fields.Many2one('construction.boq', string='New BOQ', required=True, readonly=True, ondelete='cascade')
    revision_reason = fields.Text(string='Reason for Revision', required=True)
    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True)
    approval_date = fields.Date(string='Approval Date', readonly=True)
    
    @api.model
    def create_revision(self, original_boq_id, reason):
        """
        Logic to clone the Original BOQ into a New BOQ.
        1. Checks if original is eligible (Approved/Locked).
        2. Copies the BOQ with incremented version.
        3. Creates the Revision record linking both.
        """
        original_boq = self.env['construction.boq'].browse(original_boq_id)
        
        # Validation: Only Approved/Locked BOQs can be revised
        if original_boq.state not in ['approved', 'locked']:
            raise ValidationError(_("Only 'Approved' or 'Locked' BOQs can be revised."))

        # 1. Clone the BOQ (Triggering .copy() on boq model)
        # We assume the default copy() method duplicates lines/sections automatically due to One2many structure
        new_version = original_boq.version + 1
        new_boq_vals = {
            'name': f"{original_boq.name} (Rev {new_version})",
            'version': new_version,
            'state': 'draft',
            'project_id': original_boq.project_id.id,
            'analytic_account_id': original_boq.analytic_account_id.id,
            'company_id': original_boq.company_id.id,
            'approved_by': False,
            'approval_date': False,
        }
        
        # Perform the copy
        new_boq = original_boq.copy(default=new_boq_vals)

        # 2. Create the Revision Record
        revision = self.create({
            'original_boq_id': original_boq.id,
            'new_boq_id': new_boq.id,
            'revision_reason': reason,
        })

        return revision