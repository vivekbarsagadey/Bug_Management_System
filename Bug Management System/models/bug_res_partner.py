# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class bug_ResPartner(models.Model):
    """ Inherits partner and adds Bugs information in the partner form """
    _inherit = 'res.partner'

    bug_ids = fields.One2many('project.bug', 'partner_id', string='Bugs')
    bug_count = fields.Integer(compute='_compute_bug_count', string='# Bugs')

    def _compute_bug_count(self):
        fetch_data = self.env['project.bug'].read_group([('partner_id', 'in', self.ids)], ['partner_id'], ['partner_id'])
        result = dict((data['partner_id'][0], data['partner_id_count']) for data in fetch_data)
        for partner in self:
            partner.bug_count = result.get(partner.id, 0)
