# -*- coding: utf-8 -*-
{
    'name': 'External Odoo',
    'version': '10.0.1.0.0',    
    'author': 'Odoo Nodriza Tech (ONT)',
    'website': 'https://nodrizatech.com/',
    'category': 'Tools',
    'license': 'AGPL-3',
    'depends': ['base', 'sale', 'website_quote', 'utm_websites', 'tracking_arelux', 'arelux_partner_questionnaire', 'delivery'],
    'data': [
        'data/ir_configparameter_data.xml',
        'data/ir_cron.xml',
        'security/ir.model.access.csv',
        'views/external_odoo_view.xml',
    ],
    'installable': True,
    'auto_install': False,    
}