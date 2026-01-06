# -*- coding: utf-8 -*-
from odoo import models, fields

class ProjectTask(models.Model):
    _inherit = 'project.task'

    activity_code = fields.Char(string='Activity Code', help="Code used to link with BOQ lines for cost control.")

    _sql_constraints = [
        ('uniq_activity_code_project', 'unique(project_id, activity_code)', 'Activity Code must be unique per project.')
    ]