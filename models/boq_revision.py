# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class ConstructionBOQRevision(models.Model):
    _name = 'construction.boq.revision'
    _description = 'BOQ Revision History'
    _order = 'create_date desc'
    _rec_name = 'display_name'
    
    # Performance Optimization: Added indexes for frequently searched fields
    original_boq_id = fields.Many2one(
        'construction.boq',
        string='Original BOQ (Snapshot)',
        required=True,
        readonly=True,
        ondelete='restrict',
        index=True, # Added index for faster searches
        help="Reference to the original BOQ snapshot"
    )
   
    new_boq_id = fields.Many2one(
        'construction.boq',
        string='New BOQ (Current)',
        required=True,
        readonly=True,
        ondelete='cascade',
        index=True, # Added index for faster searches
        help="Reference to the current BOQ after revision"
    )
   
    revision_reason = fields.Text(
        string='Reason for Revision',
        required=True,
        help="Detailed explanation for the BOQ revision"
    )
   
    approved_by = fields.Many2one(
        'res.users',
        string='Approved By',
        readonly=True,
        index=True, # Added index for user-based filtering
        help="User who approved this revision"
    )
   
    approval_date = fields.Date(
        string='Approval Date',
        readonly=True,
        help="Date when the revision was approved"
    )
   
    # Performance Optimization: Computed field for better UI performance
    display_name = fields.Char(
        string='Revision Reference',
        compute='_compute_display_name',
        store=True, # Stored for faster searches
        index=True, # Indexed for better search performance
    )
   
    # Performance Optimization: Related fields to avoid extra queries
    original_boq_name = fields.Char(
        related='original_boq_id.name',
        string='Original BOQ Name',
        store=True, # Stored to avoid N+1 query problem
        readonly=True,
        help="Name of the original BOQ"
    )
   
    new_boq_name = fields.Char(
        related='new_boq_id.name',
        string='New BOQ Name',
        store=True, # Stored to avoid N+1 query problem
        readonly=True,
        help="Name of the new BOQ"
    )
   
    # Performance Optimization: Track status for filtering
    state = fields.Selection(
        related='new_boq_id.state',
        string='BOQ State',
        store=True, # Stored for faster filtering
        readonly=True,
        help="Current state of the BOQ"
    )
   
    # Performance Optimization: Indexed date fields for range queries
    create_date = fields.Datetime(
        string='Created On',
        readonly=True,
        index=True, # Indexed for faster date-based filtering
    )
   
    # Performance Optimization: Archive instead of delete for historical data
    active = fields.Boolean(
        string='Active',
        default=True,
        help="If unchecked, it will allow you to hide the revision without removing it."
    )
   
    # Performance Optimization: SQL constraints for data integrity
    _sql_constraints = [
        ('unique_revision_pair',
         'UNIQUE(original_boq_id, new_boq_id)',
         'A revision record already exists for this BOQ pair.'),
    ]
    
    @api.depends('original_boq_id', 'new_boq_id', 'create_date')
    def _compute_display_name(self):
        """Compute display name for better UI performance"""
        for revision in self:
            if revision.original_boq_id and revision.new_boq_id:
                revision.display_name = f"Revision: {revision.original_boq_id.name} → {revision.new_boq_id.name}"
            else:
                revision.display_name = f"Revision {revision.id}"
    
    @api.constrains('original_boq_id', 'new_boq_id')
    def _check_boq_relationship(self):
        """Validate BOQ relationship to prevent circular revisions"""
        for revision in self:
            if revision.original_boq_id == revision.new_boq_id:
                raise ValidationError(_('Original BOQ and New BOQ cannot be the same.'))
           
            # Check if new_boq_id is already an original in another revision
            # This prevents creating revision chains that are too long
            existing_revision = self.search([
                ('original_boq_id', '=', revision.new_boq_id.id)
            ], limit=1)
           
            if existing_revision and existing_revision.id != revision.id:
                raise ValidationError(
                    _('This BOQ is already an original in another revision. '
                      'Please update the existing revision instead.')
                )
    
    def name_get(self):
        """Optimized name_get to avoid multiple queries"""
        # Use prefetching for better performance
        self.mapped('original_boq_id.name')
        self.mapped('new_boq_id.name')
       
        return [(record.id, record.display_name) for record in self]
    
    # FIXED: Updated _search method for Odoo 18 compatibility
    @api.model
    def _search(self, args, offset=0, limit=None, order=None):
        """Optimize search queries with proper indexing"""
        # Add default ordering if not specified
        if not order:
            order = self._order
       
        # FIXED: Call super without count parameter (Odoo 18 compatibility)
        return super(ConstructionBOQRevision, self)._search(
            args, offset=offset, limit=limit, order=order
        )
    
    # Performance Optimization: Batch methods for better ORM usage
    def get_related_boqs(self):
        """Get all related BOQs in a single query"""
        boq_ids = self.mapped('original_boq_id') + self.mapped('new_boq_id')
        return boq_ids
    
    # Performance Optimization: Add security rules for better access control
    @api.model
    def _get_default_team(self):
        """Get default construction team for access control"""
        # This would typically be implemented based on your business logic
        return self.env['construction.team'].search([], limit=1)
    
    def action_archive(self):
        """Archive revision instead of deleting"""
        self.write({'active': False})
        return True
    
    def action_unarchive(self):
        """Unarchive revision"""
        self.write({'active': True})
        return True