# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class bug_ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    module_project_forecast = fields.Boolean(string="Forecasts")
    module_hr_timesheet = fields.Boolean(string="Bug Logs")
    group_subbug_project = fields.Boolean("Sub-bugs", implied_group="project.group_subbug_project")
    group_project_rating = fields.Boolean("Use Rating on Project", implied_group='project.group_project_rating')
