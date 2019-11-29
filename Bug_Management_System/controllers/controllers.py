# -*- coding: utf-8 -*-
from odoo import http

# class ProjectBugs(http.Controller):
#     @http.route('/project_bugs/project_bugs/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/project_bugs/project_bugs/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('project_bugs.listing', {
#             'root': '/project_bugs/project_bugs',
#             'objects': http.request.env['project_bugs.project_bugs'].search([]),
#         })

#     @http.route('/project_bugs/project_bugs/objects/<model("project_bugs.project_bugs"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('project_bugs.object', {
#             'object': obj
#         })