# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class ConstructionBOQ(models.Model):
     _name = 'construction.boq'
     _description = 'Construction Bill of Quantities'
     _inherit = ['mail.thread', 'mail.activity.mixin'] # Enables chatter and audit trail
     _order = 'id desc'

     # We will add the fields here in Task 2.3