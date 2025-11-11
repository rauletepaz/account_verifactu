# -*- coding: utf-8 -*-

from odoo import api, fields, models, _



class VeriFactuConfiguration(models.TransientModel):
    #_name = 'mail_move_message.config.settings'
    _inherit = 'res.config.settings'


    verifactu_runing = fields.Boolean( default='False', string='You can activate/deactivate verifactu here')
    
    verifactu_runing_method = fields.Selection([
        ('no_production', 'Runing for testing'),
        ('production', 'Runing for work'),
        ], default='no_production', string='Runing method',
        )
    '''
    verifactu_sif_verificable = fields.Selection([
        ('no_verificable', 'SIF no verificable'),
        ('verificable', 'SIF verificable'),
        ], default='no_verificable', string='SIF (Sistemas Informáticos de Facturación) type', 
        help="""SIF (Sistemas Informáticos de Facturación) type:
Verificable means AEAT can vefify your SIF"""
        )
        '''
    verifactu_endpoint_no_produccion_verificable = fields.Char(string='Runing for test SIF verificable')
    verifactu_endpoint_no_produccion_no_verificable = fields.Char(string='Runing for test SIF no verificable')
    verifactu_endpoint_produccion_verificable = fields.Char(string='Runing for production SIF verificable')
    verifactu_endpoint_produccion_no_verificable = fields.Char(string='Runing for production SIF no verificable')
    
    verifactu_simplified_invoices = fields.Boolean(string='Use of simplified invoices on verifactu', help='Simplified invoices like ticket of sale with no customer idenfied')
    
    @api.model
    def get_values(self):
        res = super(VeriFactuConfiguration, self).get_values()
        verifactu_runing = self.env["ir.config_parameter"].get_param("account_verifactu.verifactu_runing", default=None)
        verifactu_runing_method = self.env["ir.config_parameter"].get_param("account_verifactu.verifactu_runing_method", default=None)
        #verifactu_sif_verificable = self.env["ir.config_parameter"].get_param("account_verifactu.verifactu_sif_verificable", default=None)
        verifactu_endpoint_no_produccion_verificable = self.env["ir.config_parameter"].get_param("account_verifactu.verifactu_endpoint_no_produccion_verificable", default=None)
        verifactu_endpoint_no_produccion_no_verificable = self.env["ir.config_parameter"].get_param("account_verifactu.verifactu_endpoint_no_produccion_no_verificable", default=None)
        verifactu_endpoint_produccion_verificable = self.env["ir.config_parameter"].get_param("account_verifactu.verifactu_endpoint_produccion_verificable", default=None)
        verifactu_endpoint_produccion_no_verificable = self.env["ir.config_parameter"].get_param("account_verifactu.verifactu_endpoint_produccion_no_verificable", default=None)
        verifactu_simplified_invoices = self.env["ir.config_parameter"].get_param("account_verifactu.verifactu_simplified_invoices", default=None)
        res.update(
            verifactu_runing = verifactu_runing,
            verifactu_runing_method = verifactu_runing_method,
            #verifactu_sif_verificable = verifactu_sif_verificable,
            verifactu_endpoint_no_produccion_verificable = verifactu_endpoint_no_produccion_verificable,
            verifactu_endpoint_no_produccion_no_verificable = verifactu_endpoint_no_produccion_no_verificable,
            verifactu_endpoint_produccion_verificable = verifactu_endpoint_produccion_verificable,
            verifactu_endpoint_produccion_no_verificable = verifactu_endpoint_produccion_no_verificable,
            verifactu_simplified_invoices = verifactu_simplified_invoices
        )
        return res

    def set_values(self):
        super(VeriFactuConfiguration, self).set_values()
        self.env['ir.config_parameter'].set_param("account_verifactu.verifactu_runing", bool(self.verifactu_runing))
        self.env['ir.config_parameter'].set_param("account_verifactu.verifactu_runing_method", self.verifactu_runing_method or '')
        #self.env['ir.config_parameter'].set_param("account_verifactu.verifactu_sif_verificable", self.verifactu_sif_verificable or '')
        self.env['ir.config_parameter'].set_param("account_verifactu.verifactu_endpoint_no_produccion_verificable", self.verifactu_endpoint_no_produccion_verificable or '')
        self.env['ir.config_parameter'].set_param("account_verifactu.verifactu_endpoint_no_produccion_no_verificable", self.verifactu_endpoint_no_produccion_no_verificable or '')
        self.env['ir.config_parameter'].set_param("account_verifactu.verifactu_endpoint_produccion_verificable", self.verifactu_endpoint_produccion_verificable or '')
        self.env['ir.config_parameter'].set_param("account_verifactu.verifactu_endpoint_produccion_no_verificable", self.verifactu_endpoint_produccion_no_verificable or '')

        self.env['ir.config_parameter'].set_param("account_verifactu.verifactu_simplified_invoices", self.verifactu_simplified_invoices or '')

    
