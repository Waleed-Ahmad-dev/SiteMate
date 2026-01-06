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
        Creates a revision by cloning the Original BOQ.
        """
        original_boq = self.env['construction.boq'].browse(original_boq_id)
        
        if original_boq.state not in ['approved', 'locked']:
            raise ValidationError(_("Only 'Approved' or 'Locked' BOQs can be revised."))

        # 1. Clone the BOQ
        # Increment version
        new_version = original_boq.version + 1
        
        default_vals = {
            'name': f"{original_boq.name} (Rev {new_version})",
            'version': new_version,
            'state': 'draft',
            'project_id': original_boq.project_id.id,
            'analytic_account_id': original_boq.analytic_account_id.id,
            'company_id': original_boq.company_id.id,
            'approved_by': False,
            'approval_date': False,
            # Reset tracking
        }
        
        # This will copy the BOQ header and associated One2many lines automatically
        new_boq = original_boq.copy(default=default_vals)

        # 2. Create the Revision Record
        revision = self.create({
            'original_boq_id': original_boq.id,
            'new_boq_id': new_boq.id,
            'revision_reason': reason,
            'approved_by': self.env.user.id,
            'approval_date': fields.Date.today(),
        })

        # 3. Message logging
        original_boq.message_post(body=f"Revision {new_version} created: {reason}")
        new_boq.message_post(body=f"Created as Revision {new_version} from {original_boq.name}. Reason: {reason}")

        return revision