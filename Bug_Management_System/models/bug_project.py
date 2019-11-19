# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import timedelta

from odoo import api, fields, models, tools, SUPERUSER_ID, _
from odoo.exceptions import UserError, AccessError, ValidationError
from odoo.tools.safe_eval import safe_eval


class ProjectBugType(models.Model):
    _name = 'project.bug.type'
    _description = 'Bug Stage'
    _order = 'sequence, id'

    def _get_default_project_ids(self):
        default_project_id = self.env.context.get('default_project_id')
        return [default_project_id] if default_project_id else None

    name = fields.Char(string='Stage Name', required=True, translate=True)
    description = fields.Text(translate=True)
    sequence = fields.Integer(default=1)
    project_ids = fields.Many2many('project.project', 'project_bug_type_rel', 'type_id', 'project_id', string='Projects',
        default=_get_default_project_ids)
    legend_priority = fields.Char(
        string='Starred Explanation', translate=True,
        help='Explanation text to help users using the star on bugs in this stage.')
    legend_blocked = fields.Char(
        'Red Kanban Label', default=lambda s: _('Blocked'), translate=True, required=True,
        help='Override the default value displayed for the blocked state for kanban selection, when the bug is in that stage.')
    legend_done = fields.Char(
        'Green Kanban Label', default=lambda s: _('Ready for Next Stage'), translate=True, required=True,
        help='Override the default value displayed for the done state for kanban selection, when the bug is in that stage.')
    legend_normal = fields.Char(
        'Grey Kanban Label', default=lambda s: _('In Progress'), translate=True, required=True,
        help='Override the default value displayed for the normal state for kanban selection, when the bug is in that stage.')
    mail_template_id = fields.Many2one(
        'mail.template',
        string='Email Template',
        domain=[('model', '=', 'project.bug')],
        help="If set an email will be sent to the customer when the bug reaches this step.")
    fold = fields.Boolean(string='Folded in Kanban',
        help='This stage is folded in the kanban view when there are no records in that stage to display.')
    rating_template_id = fields.Many2one(
        'mail.template',
        string='Rating Email Template',
        domain=[('model', '=', 'project.bug')],
        help="If set and if the project's rating configuration is 'Rating when changing stage', then an email will be sent to the customer when the bug reaches this step.")
    auto_validation_kanban_state = fields.Boolean('Automatic kanban status', default=False,
        help="Automatically modify the kanban state when the customer replies to the feedback for this stage.\n"
            " * A good feedback from the customer will update the kanban state to 'ready for the new stage' (green bullet).\n"
            " * A medium or a bad feedback will set the kanban state to 'blocked' (red bullet).\n")

    @api.multi
    def unlink(self):
        stages = self
        default_project_id = self.env.context.get('default_project_id')
        if default_project_id:
            shared_stages = self.filtered(lambda x: len(x.project_ids) > 1 and default_project_id in x.project_ids.ids)
            bugs = self.env['project.bug'].with_context(active_test=False).search([('project_id', '=', default_project_id), ('stage_id', 'in', self.ids)])
            if shared_stages and not bugs:
                shared_stages.write({'project_ids': [(3, default_project_id)]})
                stages = self.filtered(lambda x: x not in shared_stages)
        return super(ProjectBugType, stages).unlink()



class Bug(models.Model):
    _name = "project.bug"
    _description = "Bug"
    _date_name = "date_start"
    _res_model: 'project.project'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin', 'rating.mixin']
    _mail_post_access = 'read'
    _order = "priority desc, sequence, id desc"

    @api.model
    def default_get(self, fields_list):
        result = super(Bug, self).default_get(fields_list)
        # force some parent values, if needed
        if 'parent_id' in result and result['parent_id']:
            result.update(self._subbug_values_from_parent(result['parent_id']))
        return result

    @api.model
    def _get_default_partner(self):
        if 'default_project_id' in self.env.context:
            default_project_id = self.env['project.project'].browse(self.env.context['default_project_id'])
            return default_project_id.exists().partner_id

    def _get_default_stage_id(self):
        """ Gives default stage_id """
        project_id = self.env.context.get('default_project_id')
        if not project_id:
            return False
        return self.stage_find(project_id, [('fold', '=', False)])

    @api.model
    def _read_group_stage_ids(self, stages, domain, order):
        search_domain = [('id', 'in', stages.ids)]
        if 'default_project_id' in self.env.context:
            search_domain = ['|', ('project_ids', '=', self.env.context['default_project_id'])] + search_domain

        stage_ids = stages._search(search_domain, order=order, access_rights_uid=SUPERUSER_ID)
        return stages.browse(stage_ids)

    active = fields.Boolean(default=True)
    name = fields.Char(string='Title', track_visibility='always', required=True, index=True)
    description = fields.Html(string='Description')
    Replicate = fields.Html(string='Steps To Replicate')
    Expected = fields.Html(string='Expected Result')
    Actual = fields.Html(string='Actual Result')
    Solution = fields.Html(string='Solution')
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ], default='0', index=True, string="Priority")
    sequence = fields.Integer(string='Sequence', index=True, default=10,
        help="Gives the sequence order when displaying a list of bugs.")
    stage_id = fields.Many2one('project.bug.type', string='Stage', ondelete='restrict', track_visibility='onchange',required=True, index=True,
        default=_get_default_stage_id, group_expand='_read_group_stage_ids',
        domain="[('project_ids', '=', project_id)]", copy=False)
    tag_ids = fields.Many2many('project.tags', string='Issue Type', oldname='categ_ids', required=True)
    bug_priority = fields.Many2many('bug.priority', string='Bug Priority', required=True)
    version = fields.Many2many('bug.version', string='Version')
    fix_version = fields.Many2many('fix.version', string='Fixed Version')
    client_urgency = fields.Many2many('client.urgency', string='Client Urgency')
    Reside = fields.Many2many('issue.reside', string='Issue Resides in',required=True )
    kanban_state = fields.Selection([
        ('normal', 'Gray'),
        ('done', 'Green'),
        ('blocked', 'Red')], string='Kanban State',
        copy=False, default='normal', required=True)
    kanban_state_label = fields.Char(compute='_compute_kanban_state_label', string='Kanban State Label', track_visibility='onchange')
    create_date = fields.Datetime("Created On", readonly=True, index=True)
    write_date = fields.Datetime("Last Updated On", readonly=True, index=True)
    date_start = fields.Datetime(string='Starting Date',
    default=fields.Datetime.now,
    index=True, copy=False)
    date_end = fields.Datetime(string='Ending Date', index=True, copy=False)
    date_assign = fields.Datetime(string='Build Date', index=True, copy=False, readonly=True)
    date_deadline = fields.Date(string='Deadline', index=True, copy=False, track_visibility='onchange')
    date_last_stage_update = fields.Datetime(string='Last Stage Update',
        index=True,
        copy=False,
        readonly=True) 
    project_id = fields.Many2one('project.project',string='Project',
        default=lambda self: self.env.context.get('default_project_id'),
        index=True,
        track_visibility='onchange',
        change_default=True)
    notes = fields.Text(string='Notes')
    planned_hours = fields.Float("Planned Hours", help='It is the time planned to achieve the bug. If this document has sub-bugs, it means the time needed to achieve this bugs and its childs.',track_visibility='onchange')
    subbug_planned_hours = fields.Float("Subbugs", compute='_compute_subbug_planned_hours', help="Computed using sum of hours planned of all subbugs created from main bug. Usually these hours are less or equal to the Planned Hours (of main bug).")
    user_id = fields.Many2one('res.users',
        string='Assigned to',
        default=lambda self: self.env.uid,
        index=True, track_visibility='always')
    client_id = fields.Many2one('res.partner',
        string='Client',
        default=lambda self: self.env.uid,
        index=True, track_visibility='always')
    creater_id = fields.Many2one('res.partner',
        string='Submitted by',
        default=lambda self: self.env.uid,
        index=True, track_visibility='always')
    partner_id = fields.Many2one('res.partner',
        string='Customer',
        default=lambda self: self._get_default_partner())
    manager_id = fields.Many2one('res.users', string='Project Manager', related='project_id.user_id', readonly=True, related_sudo=False)
    company_id = fields.Many2one('res.company',
        string='Company',
        default=lambda self: self.env['res.company']._company_default_get())
    color = fields.Integer(string='Color Index')
    user_email = fields.Char(related='user_id.email', string='User Email', readonly=True, related_sudo=False)
    attachment_ids = fields.One2many('ir.attachment', compute='_compute_attachment_ids', string="Main Attachments",
        help="Attachment that don't come from message.")
    # In the domain of displayed_image_id, we couln't use attachment_ids because a one2many is represented as a list of commands so we used res_model & res_id
    displayed_image_id = fields.Many2one('ir.attachment', domain="[('res_model', '=', 'project.bug'), ('res_id', '=', id), ('mimetype', 'ilike', 'image')]", string='Cover Image')
    legend_blocked = fields.Char(related='stage_id.legend_blocked', string='Kanban Blocked Explanation', readonly=True, related_sudo=False)
    legend_done = fields.Char(related='stage_id.legend_done', string='Kanban Valid Explanation', readonly=True, related_sudo=False)
    legend_normal = fields.Char(related='stage_id.legend_normal', string='Kanban Ongoing Explanation', readonly=True, related_sudo=False)
    parent_id = fields.Many2one('project.bug', string='Parent Bug', index=True)
    child_ids = fields.One2many('project.bug', 'parent_id', string="Sub-bugs", context={'active_test': False})
    subbug_project_id = fields.Many2one('project.project', related="project_id.subtask_project_id", string='Sub-bug Project', readonly=True)
    subbug_count = fields.Integer("Sub-bug count", compute='_compute_subbug_count')
    email_from = fields.Char(string='Email', help="These people will receive email.", index=True)
    email_cc = fields.Char(string='Watchers Emails', help="""These email addresses will be added to the CC field of all inbound
        and outbound emails for this record before being sent. Separate multiple email addresses with a comma""")
    # Computed field about working time elapsed between record creation and assignation/closing.
    working_hours_open = fields.Float(compute='_compute_elapsed', string='Working hours to assign', store=True, group_operator="avg")
    working_hours_close = fields.Float(compute='_compute_elapsed', string='Working hours to close', store=True, group_operator="avg")
    working_days_open = fields.Float(compute='_compute_elapsed', string='Working days to assign', store=True, group_operator="avg")
    working_days_close = fields.Float(compute='_compute_elapsed', string='Working days to close', store=True, group_operator="avg")
    # customer portal: include comment and incoming emails in communication history
    website_message_ids = fields.One2many(domain=lambda self: [('model', '=', self._name), ('message_type', 'in', ['email', 'comment'])])

    _constraints = [(models.BaseModel._check_recursion, 'Circular references are not permitted between bugs and sub-bugs', ['parent_id'])]

    def _compute_attachment_ids(self):
        for bug in self:
            attachment_ids = self.env['ir.attachment'].search([('res_id', '=', bug.id), ('res_model', '=', 'project.bug')]).ids
            message_attachment_ids = bug.mapped('message_ids.attachment_ids').ids  # from mail_thread
            bug.attachment_ids = list(set(attachment_ids) - set(message_attachment_ids))

    @api.multi
    @api.depends('create_date', 'date_end', 'date_assign')
    def _compute_elapsed(self):
        bug_linked_to_calendar = self.filtered(
            lambda bug: bug.project_id.resource_calendar_id and bug.create_date
        )
        for bug in bug_linked_to_calendar:
            dt_create_date = fields.Datetime.from_string(bug.create_date)

            if bug.date_assign:
                dt_date_assign = fields.Datetime.from_string(bug.date_assign)
                bug.working_hours_open = bug.project_id.resource_calendar_id.get_work_hours_count(
                        dt_create_date, dt_date_assign, compute_leaves=True)
                bug.working_days_open = bug.working_hours_open / 24.0

            if bug.date_end:
                dt_date_end = fields.Datetime.from_string(bug.date_end)
                bug.working_hours_close = bug.project_id.resource_calendar_id.get_work_hours_count(
                    dt_create_date, dt_date_end, compute_leaves=True)
                bug.working_days_close = bug.working_hours_close / 24.0

        (self - bug_linked_to_calendar).update(dict.fromkeys(
            ['working_hours_open', 'working_hours_close', 'working_days_open', 'working_days_close'], 0.0))

    @api.depends('stage_id', 'kanban_state')
    def _compute_kanban_state_label(self):
        for bug in self:
            if bug.kanban_state == 'normal':
                bug.kanban_state_label = bug.legend_normal
            elif bug.kanban_state == 'blocked':
                bug.kanban_state_label = bug.legend_blocked
            else:
                bug.kanban_state_label = bug.legend_done

    def _compute_access_url(self):
        super(Bug, self)._compute_access_url()
        for bug in self:
            bug.access_url = '/my/bug/%s' % bug.id

    def _compute_access_warning(self):
        super(Bug, self)._compute_access_warning()
        for bug in self.filtered(lambda x: x.project_id.privacy_visibility != 'portal'):
            bug.access_warning = _(
                "The bug cannot be shared with the recipient(s) because the privacy of the project is too restricted. Set the privacy of the project to 'Visible by following customers' in order to make it accessible by the recipient(s).")

    @api.depends('child_ids.planned_hours')
    def _compute_subbug_planned_hours(self):
        for bug in self:
            bug.subbug_planned_hours = sum(bug.child_ids.mapped('planned_hours'))

    @api.depends('child_ids')
    def _compute_subbug_count(self):
        """ Note: since we accept only one level subbug, we can use a read_group here """
        bug_data = self.env['project.bug'].read_group([('parent_id', 'in', self.ids)], ['parent_id'], ['parent_id'])
        mapping = dict((data['parent_id'][0], data['parent_id_count']) for data in bug_data)
        for bug in self:
            bug.subbug_count = mapping.get(bug.id, 0)

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        self.email_from = self.partner_id.email

    @api.onchange('parent_id')
    def _onchange_parent_id(self):
        if self.parent_id:
            for field_name in self._subbug_implied_fields():
                self[field_name] = self.parent_id[field_name]

    @api.onchange('project_id')
    def _onchange_project(self):
        if self.project_id:
            if not self.parent_id and self.project_id.partner_id:
                self.partner_id = self.project_id.partner_id
            if self.project_id not in self.stage_id.project_ids:
                self.stage_id = self.stage_find(self.project_id.id, [('fold', '=', False)])
        else:
            self.stage_id = False

    @api.onchange('user_id')
    def _onchange_user(self):
        if self.user_id:
            self.date_start = fields.Datetime.now()

    @api.constrains('parent_id', 'child_ids')
    def _check_subbug_level(self):
        for bug in self:
            if bug.parent_id and bug.child_ids:
                raise ValidationError(_('Bug %s cannot have several subbug levels.' % (bug.name,)))

    @api.multi
    def map_bugs(self, new_project_id):
        """ copy and map bugs from old to new project """
        bugs = self.env['project.bug']
        # We want to copy archived bug, but do not propagate an active_test context key
        bug_ids = self.env['project.bug'].with_context(active_test=False).search([('project_id', '=', self.id)], order='parent_id').ids
        old_to_new_bugs = {}
        for bug in self.env['project.bug'].browse(bug_ids):
            # preserve bug name and stage, normally altered during copy
            defaults = self._map_bugs_default_valeus(bug)
            if bug.parent_id:
                # set the parent to the duplicated bug
                defaults['parent_id'] = old_to_new_bugs.get(bug.parent_id.id, False)
            new_bug = bug.copy(defaults)
            old_to_new_bugs[bug.id] = new_bug.id
            bugs += new_bug

        return self.browse(new_project_id).write({'bugs': [(6, 0, bugs.ids)]})



    
    def create(self, vals):
        # Prevent double project creation
        self = self.with_context(mail_create_nosubscribe=True)
        project = super(Project, self).create(vals)
        if not vals.get('subbug_project_id'):
            project.subbug_project_id = project.id
        if project.privacy_visibility == 'portal' and project.partner_id:
            project.message_subscribe(project.partner_id.ids)
        return project
    
    @api.multi
    def write(self, vals):
        # directly compute is_favorite to dodge allow write access right
        if 'is_favorite' in vals:
            vals.pop('is_favorite')
            self._fields['is_favorite'].determine_inverse(self)
        res = super(Project, self).write(vals) if vals else True
        if 'active' in vals:
            # archiving/unarchiving a project does it on its tasks, too
            self.with_context(active_test=False).mapped('bugs').write({'active': vals['active']})
        if vals.get('partner_id') or vals.get('privacy_visibility'):
            for project in self.filtered(lambda project: project.privacy_visibility == 'portal'):
                project.message_subscribe(project.partner_id.ids)
        return res
    
    @api.multi
    @api.returns('self', lambda value: value.id)
    def copy(self, default=None):
        if default is None:
            default = {}
        if not default.get('name'):
            default['name'] = _("%s (copy)") % (self.name)
        project = super(Bug, self).copy(default)
        if self.subbug_project_id == self:
            project.subbug_project_id = project
        for follower in self.message_follower_ids:
            project.message_subscribe(partner_ids=follower.partner_id.ids, subtype_ids=follower.subtype_ids.ids)
        if 'bugs' not in default:
            self.map_bugs(project.id)
        return project  
    

    @api.constrains('parent_id')
    def _check_parent_id(self):
        for bug in self:
            if not bug._check_recursion():
                raise ValidationError(_('Error! You cannot create recursive hierarchy of bug(s).'))

    @api.model
    def get_empty_list_help(self, help):
        tname = _("bug")
        project_id = self.env.context.get('default_project_id', False)
        if project_id:
            name = self.env['project.project'].browse(project_id).label_bugs
            if name: tname = name.lower()

        self = self.with_context(
            empty_list_help_id=self.env.context.get('default_project_id'),
            empty_list_help_model='project.project',
            empty_list_help_document_name=tname,
        )
        return super(Bug, self).get_empty_list_help(help)

    # ----------------------------------------
    # Case management
    # ----------------------------------------

    def stage_find(self, section_id, domain=[], order='sequence'):
        """ Override of the base.stage method
            Parameter of the stage search taken from the lead:
            - section_id: if set, stages must belong to this section or
              be a default stage; if not set, stages must be default
              stages
        """
        # collect all section_ids
        section_ids = []
        if section_id:
            section_ids.append(section_id)
        section_ids.extend(self.mapped('project_id').ids)
        search_domain = []
        if section_ids:
            search_domain = [('|')] * (len(section_ids) - 1)
            for section_id in section_ids:
                search_domain.append(('project_ids', '=', section_id))
        search_domain += list(domain)
        # perform search, return the first found
        return self.env['project.bug.type'].search(search_domain, order=order, limit=1).id

    # ------------------------------------------------
    # CRUD overrides
    # ------------------------------------------------

    @api.model
    def create(self, vals):
        # context: no_log, because subtype already handle this
        context = dict(self.env.context, mail_create_nolog=True)
        # force some parent values, if needed
        if 'parent_id' in vals and vals['parent_id']:
            vals.update(self._subbug_values_from_parent(vals['parent_id']))
            context.pop('default_parent_id', None)
        # for default stage
        if vals.get('project_id') and not context.get('default_project_id'):
            context['default_project_id'] = vals.get('project_id')
        # user_id change: update date_assign
        if vals.get('user_id'):
            vals['date_assign'] = fields.Datetime.now()
        # Stage change: Update date_end if folded stage and date_last_stage_update
        if vals.get('stage_id'):
            vals.update(self.update_date_end(vals['stage_id']))
            vals['date_last_stage_update'] = fields.Datetime.now()
        bug = super(Bug, self.with_context(context)).create(vals)
        return bug

    @api.multi
    def write(self, vals):
        now = fields.Datetime.now()
        # subbug: force some parent values, if needed
        if 'parent_id' in vals and vals['parent_id']:
            vals.update(self._subbug_values_from_parent(vals['parent_id']))
        # stage change: update date_last_stage_update
        if 'stage_id' in vals:
            vals.update(self.update_date_end(vals['stage_id']))
            vals['date_last_stage_update'] = now
            # reset kanban state when changing stage
            if 'kanban_state' not in vals:
                vals['kanban_state'] = 'normal'
        # user_id change: update date_assign
        if vals.get('user_id') and 'date_assign' not in vals:
            vals['date_assign'] = now

        result = super(Bug, self).write(vals)
        # rating on stage
        if 'stage_id' in vals and vals.get('stage_id'):
            self.filtered(lambda x: x.project_id.rating_status == 'stage')._send_bug_rating_mail(force_send=True)
        # subbug: update subbug according to parent values
        subbug_values_to_write = self._subbug_write_values(vals)
        if subbug_values_to_write:
            subbugs = self.filtered(lambda bug: not bug.parent_id).mapped('child_ids')
            if subbugs:
                subbugs.write(subbug_values_to_write)
        return result

    def update_date_end(self, stage_id):
        project_bug_type = self.env['project.bug.type'].browse(stage_id)
        if project_bug_type.fold:
            return {'date_end': fields.Datetime.now()}
        return {'date_end': False}

    # ---------------------------------------------------
    # Subbugs
    # ---------------------------------------------------

    @api.model
    def _subbug_implied_fields(self):
        """ Return the list of field name to apply on subbug when changing parent_id or when updating parent bug. """
        return ['partner_id', 'email_from']

    @api.multi
    def _subbug_write_values(self, values):
        """ Return the values to write on subbug when `values` is written on parent bugs
            :param values: dict of values to write on parent
        """
        result = {}
        for field_name in self._subbug_implied_fields():
            if field_name in values:
                result[field_name] = values[field_name]
        return result

    def _subbug_values_from_parent(self, parent_id):
        """ Get values for subbug implied field of the given"""
        result = {}
        parent_bug = self.env['project.bug'].browse(parent_id)
        for field_name in self._subbug_implied_fields():
            result[field_name] = parent_bug[field_name]
        return self._convert_to_write(result)

    # ---------------------------------------------------
    # Mail gateway
    # ---------------------------------------------------

    @api.multi
    def _track_template(self, tracking):
        res = super(Bug, self)._track_template(tracking)
        test_bug = self[0]
        changes, tracking_value_ids = tracking[test_bug.id]
        if 'stage_id' in changes and test_bug.stage_id.mail_template_id:
            res['stage_id'] = (test_bug.stage_id.mail_template_id, {
                'auto_delete_message': True,
                'subtype_id': self.env['ir.model.data'].xmlid_to_res_id('mail.mt_note'),
                'notif_layout': 'mail.mail_notification_light'
            })
        return res

    @api.multi
    def _track_subtype(self, init_values):
        self.ensure_one()
        if 'kanban_state_label' in init_values and self.kanban_state == 'blocked':
            return 'project.mt_bug_blocked'
        elif 'kanban_state_label' in init_values and self.kanban_state == 'done':
            return 'project.mt_bug_ready'
        elif 'stage_id' in init_values and self.stage_id and self.stage_id.sequence <= 1:  # start stage -> new
            return 'project.mt_bug_new'
        elif 'stage_id' in init_values:
            return 'project.mt_bug_stage'
        return super(Bug, self)._track_subtype(init_values)

    @api.multi
    def _notify_get_groups(self, message, groups):
        """ Handle project users and managers recipients that can assign
        bugs and create new one directly from notification emails. Also give
        access button to portal users and portal customers. If they are notified
        they should probably have access to the document. """
        groups = super(Bug, self)._notify_get_groups(message, groups)

        self.ensure_one()

        project_user_group_id = self.env.ref('project.group_project_user').id
        new_group = (
            'group_project_user',
            lambda pdata: pdata['type'] == 'user' and project_user_group_id in pdata['groups'],
            {},
        )

        if not self.user_id and not self.stage_id.fold:
            take_action = self._notify_get_action_link('assign')
            project_actions = [{'url': take_action, 'title': _('I take it')}]
            new_group[2]['actions'] = project_actions

        groups = [new_group] + groups

        for group_name, group_method, group_data in groups:
            if group_name == 'customer':
                continue
            group_data['has_button_access'] = True

        return groups

    @api.multi
    def _notify_get_reply_to(self, default=None, records=None, company=None, doc_names=None):
        """ Override to set alias of bugs to their project if any. """
        aliases = self.sudo().mapped('project_id')._notify_get_reply_to(default=default, records=None, company=company, doc_names=None)
        res = {bug.id: aliases.get(bug.project_id.id) for bug in self}
        leftover = self.filtered(lambda rec: not rec.project_id)
        if leftover:
            res.update(super(Bug, leftover)._notify_get_reply_to(default=default, records=None, company=company, doc_names=doc_names))
        return res

    @api.multi
    def email_split(self, msg):
        email_list = tools.email_split((msg.get('to') or '') + ',' + (msg.get('cc') or ''))
        # check left-part is not already an alias
        aliases = self.mapped('project_id.alias_name')
        return [x for x in email_list if x.split('@')[0] not in aliases]

    @api.model
    def message_new(self, msg, custom_values=None):
        """ Overrides mail_thread message_new that is called by the mailgateway
            through message_process.
            This override updates the document according to the email.
        """
        # remove default author when going through the mail gateway. Indeed we
        # do not want to explicitly set user_id to False; however we do not
        # want the gateway user to be responsible if no other responsible is
        # found.
        create_context = dict(self.env.context or {})
        create_context['default_user_id'] = False
        if custom_values is None:
            custom_values = {}
        defaults = {
            'name': msg.get('subject') or _("No Subject"),
            'email_from': msg.get('from'),
            'email_cc': msg.get('cc'),
            'planned_hours': 0.0,
            'partner_id': msg.get('author_id')
        }
        defaults.update(custom_values)

        bug = super(Bug, self.with_context(create_context)).message_new(msg, custom_values=defaults)
        email_list = bug.email_split(msg)
        partner_ids = [p for p in bug._find_partner_from_emails(email_list, force_create=False) if p]
        bug.message_subscribe(partner_ids)
        return bug

    @api.multi
    def message_update(self, msg, update_vals=None):
        """ Override to update the bug according to the email. """
        email_list = self.email_split(msg)
        partner_ids = [p for p in self._find_partner_from_emails(email_list, force_create=False) if p]
        self.message_subscribe(partner_ids)
        return super(Bug, self).message_update(msg, update_vals=update_vals)

    @api.multi
    def message_get_suggested_recipients(self):
        recipients = super(Bug, self).message_get_suggested_recipients()
        for bug in self:
            if bug.partner_id:
                reason = _('Customer Email') if bug.partner_id.email else _('Customer')
                bug._message_add_suggested_recipient(recipients, partner=bug.partner_id, reason=reason)
            elif bug.email_from:
                bug._message_add_suggested_recipient(recipients, email=bug.email_from, reason=_('Customer Email'))
        return recipients

    @api.multi
    def _notify_specific_email_values(self, message):
        res = super(Bug, self)._notify_specific_email_values(message)
        try:
            headers = safe_eval(res.get('headers', dict()))
        except Exception:
            headers = {}
        if self.project_id:
            current_objects = [h for h in headers.get('X-Odoo-Objects', '').split(',') if h]
            current_objects.insert(0, 'project.project-%s, ' % self.project_id.id)
            headers['X-Odoo-Objects'] = ','.join(current_objects)
        if self.tag_ids:
            headers['X-Odoo-Tags'] = ','.join(self.tag_ids.mapped('name'))
        res['headers'] = repr(headers)
        return res

    def _message_post_after_hook(self, message, *args, **kwargs):
        if self.email_from and not self.partner_id:
            # we consider that posting a message with a specified recipient (not a follower, a specific one)
            # on a document without customer means that it was created through the chatter using
            # suggested recipients. This heuristic allows to avoid ugly hacks in JS.
            new_partner = message.partner_ids.filtered(lambda partner: partner.email == self.email_from)
            if new_partner:
                self.search([
                    ('partner_id', '=', False),
                    ('email_from', '=', new_partner.email),
                    ('stage_id.fold', '=', False)]).write({'partner_id': new_partner.id})
        return super(Bug, self)._message_post_after_hook(message, *args, **kwargs)

    def action_assign_to_me(self):
        self.write({'user_id': self.env.user.id})

    def action_open_parent_bug(self):
        return {
            'name': _('Parent Bug'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'project.bug',
            'res_id': self.parent_id.id,
            'type': 'ir.actions.act_window'
        }

    def action_subbug(self):
        action = self.env.ref('project.project_bug_action_sub_bug').read()[0]
        ctx = self.env.context.copy()
        ctx.update({
            'default_parent_id': self.id,
            'default_project_id': self.env.context.get('project_id', self.project_id.id),
            'default_name': self.env.context.get('name', self.name) + ':',
            'default_partner_id': self.env.context.get('partner_id', self.partner_id.id),
            'search_default_project_id': self.env.context.get('project_id', self.project_id.id),
        })
        action['context'] = ctx
        action['domain'] = [('id', 'child_of', self.id), ('id', '!=', self.id)]
        return action

    # ---------------------------------------------------
    # Rating business
    # ---------------------------------------------------

    def _send_bug_rating_mail(self, force_send=False):
        for bug in self:
            rating_template = bug.stage_id.rating_template_id
            if rating_template:
                bug.rating_send_request(rating_template, lang=bug.partner_id.lang, force_send=force_send)

    def rating_get_partner_id(self):
        res = super(bug, self).rating_get_partner_id()
        if not res and self.project_id.partner_id:
            return self.project_id.partner_id
        return res

    @api.multi
    def rating_apply(self, rate, token=None, feedback=None, subtype=None):
        return super(Bug, self).rating_apply(rate, token=token, feedback=feedback, subtype="project.mt_bug_rating")

    def rating_get_parent(self):
        return 'project_id'


class ProjectTags(models.Model):
    """ Tags of project's bugs """
    _name = "project.tags"
    _description = "Project Tags"

    name = fields.Char(required=True)
    color = fields.Integer(string='Color Index')

    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Tag name already exists!"),
    ]
    
class ProjectTags(models.Model):
    """ Tags of project's bugs """
    _name = "bug.priority"
    _description = "Bug Priority "

    name = fields.Char(required=True)
    color = fields.Integer(string='Color Index')

    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Tag name already exists!"),
    ]
    
class ProjectReside(models.Model):
    """ Tags of project's bugs """
    _name = "issue.reside"
    _description = "Issue Resides In"

    name = fields.Char(required=True)
    color = fields.Integer(string='Color Index')

    _sql_constraints = [
        ('name_uniq', 'unique (name)', "name already exists!"),
    ]

class ProjectClient(models.Model):
    """ Tags of project's bugs """
    _name = "client.urgency"
    _description = "Client urgency"

    name = fields.Char(required=True)
    color = fields.Integer(string='Color Index')

    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Client name already exists!"),
    ]
class ProjectVersion(models.Model):
    """ Tags of project's bugs """
    _name = "bug.version"
    _description = "Bug Version"

    name = fields.Char(required=True)
    color = fields.Integer(string='Color Index')

    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Version already exists!"),
    ]    

class ProjectFixVersion(models.Model):
    """ Tags of project's bugs """
    _name = "fix.version"
    _description = "fix version"

    name = fields.Char(required=True)
    color = fields.Integer(string='Color Index')

    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Version already exists!"),
    ]
