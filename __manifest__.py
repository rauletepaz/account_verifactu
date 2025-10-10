# -*- coding: utf-8 -*-
{
    'name': "Veri*Factu",
    'summary': """Spain Veri*Factu law adaptation""",
    'author': "Raul Paz from Visualcom S.L.",
    'category': 'Accounting & Finance',
    'version': '1.0',
    'website': "http://www.visualcom.es",
    'depends': ['account'],
    'data': [
        'data/ir_config_parameters.xml',
        'views/res_company_view.xml',
        'views/res_config_settings_view.xml',
        'views/account_invoice_view.xml',
        'views/account_invoice_verifactu_view.xml',
        'views/account_tax_view.xml',
        'reports/account_verifactu_report.xml',
    ],
    'license': 'AGPL-3',
}