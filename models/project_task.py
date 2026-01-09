# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ProjectTask(models.Model):
    _inherit = 'project.task'

    activity_code = fields.Char(
        string='Activity Code',
        help="Code used to link with BOQ lines for cost control.",
        index=True,  # Added index for faster searches/filtering
        copy=False  # Prevent copying when duplicating tasks
    )

    _sql_constraints = [
        ('uniq_activity_code_project', 
         'UNIQUE(project_id, activity_code)', 
         'Activity Code must be unique per project.')
    ]

    @api.constrains('activity_code', 'project_id')
    def _check_activity_code_uniqueness(self):
        """Additional Python constraint for better validation messages and bulk operations."""
        for task in self:
            if task.activity_code:
                # Only check if activity_code is not empty
                existing = self.search([
                    ('project_id', '=', task.project_id.id),
                    ('activity_code', '=', task.activity_code),
                    ('id', '!=', task.id)
                ], limit=1)
                if existing:
                    raise ValidationError(
                        f"Activity Code '{task.activity_code}' already exists for this project."
                    )

    @api.model
    def create(self, vals_list):
        """Optimize create for bulk operations."""
        # If activity_code is provided, ensure proper formatting
        if isinstance(vals_list, dict):
            vals_list = [vals_list]
        
        for vals in vals_list:
            if 'activity_code' in vals and vals.get('activity_code'):
                vals['activity_code'] = vals['activity_code'].strip().upper()
        
        return super().create(vals_list)

    def write(self, vals):
        """Optimize write for bulk operations."""
        if 'activity_code' in vals and vals.get('activity_code'):
            vals['activity_code'] = vals['activity_code'].strip().upper()
        return super().write(vals)

    def copy(self, default=None):
        """Prevent copying activity_code by default to avoid constraint violations."""
        if default is None:
            default = {}
        # Ensure activity_code is not copied unless explicitly specified
        if 'activity_code' not in default:
            default['activity_code'] = False
        return super().copy(default)

    @api.model
    def _name_search(self, name='', args=None, operator='ilike', limit=100, name_get_uid=None):
        """Optimize search for activity_code."""
        if args is None:
            args = []
        
        # If searching by code prefix (common pattern), optimize the query
        if operator in ('=', 'ilike', 'like') and name:
            # Try to match by activity_code first as it's likely more specific
            tasks = self.search(
                args + [('activity_code', operator, name)], 
                limit=limit
            )
            if tasks:
                return tasks.ids
        
        return super()._name_search(name, args, operator, limit, name_get_uid)