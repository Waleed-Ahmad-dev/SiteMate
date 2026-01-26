# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class SaleOrderTemplate(models.Model):
    _inherit = 'sale.order.template'

    def action_create_boq(self):
        """
        Open a new Construction BOQ form with this template pre-selected.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create BOQ from Template'),
            'res_model': 'construction.boq',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_quotation_template_id': self.id,
                'default_name': self.name,
            }
        }