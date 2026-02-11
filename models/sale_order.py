# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    boq_ids = fields.One2many('construction.boq', 'sale_order_id', string='BOQs')
    boq_count = fields.Integer(compute='_compute_boq_count', string='BOQ Count')

    @api.depends('boq_ids')
    def _compute_boq_count(self):
        for order in self:
            order.boq_count = len(order.boq_ids)

    def action_create_boq(self):
        """
        Action to create a Construction BOQ from a Confirmed Sales Order.
        Opens the BOQ form with default values populated from the SO.
        """
        self.ensure_one()
        
        # [FIX] In Odoo 18, sale.order does not have 'analytic_account_id'.
        # We must fetch the analytic account from the related Project.
        analytic_account_id = False
        if self.project_id and self.project_id.account_id:
            analytic_account_id = self.project_id.account_id.id

        return {
            'type': 'ir.actions.act_window',
            'name': _('Create BOQ'),
            'res_model': 'construction.boq',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_sale_order_id': self.id,
                'default_project_id': self.project_id.id if self.project_id else False,
                'default_analytic_account_id': analytic_account_id,
                'default_company_id': self.company_id.id,
                'default_name': f"{self.name} - BOQ",
            }
        }

    def action_view_boq(self):
        """
        Smart button action to view related BOQs.
        """
        self.ensure_one()
        boqs = self.boq_ids
        action = self.env['ir.actions.act_window']._for_xml_id('sitemate.action_construction_boq')
        
        if len(boqs) > 1:
            action['domain'] = [('id', 'in', boqs.ids)]
        elif boqs:
            action['views'] = [(self.env.ref('sitemate.view_construction_boq_form').id, 'form')]
            action['res_id'] = boqs.id
        
        # Pass default context for creating new BOQ from this view
        action['context'] = {
            'default_sale_order_id': self.id,
            'default_project_id': self.project_id.id if self.project_id else False,
        }
        return action