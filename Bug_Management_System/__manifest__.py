# -*- coding: utf-8 -*-
{
    'name': "Bugs Management System",

    'summary': """
        The Purpose of this module is management of Bugs in Project""",

    'description': """
        Organize and schedule your Bugs
    """,

    'author': "Whiz IT Services",
    'website': "http://www.whizit.co.in",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/12.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Project',
    'version': '12.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 
		'project',
	       ],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/rating_views.xml',
        'views/bug_view.xml',
	'data/stage_data.xml',  
	'security/ir.model.access.csv'
         
    ],
    
    'images':[
        'static/description/banner.png',
        'static/description/icon.png',
        'static/description/index.html',
        ],
    # only loaded in demonstration mode
    'demo': [
         
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}
