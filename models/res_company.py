# -*- coding: utf-8 -*-

import re

from odoo import api, fields, models, _

class res_company(models.Model):
    _inherit = 'res.company'
    
    verifactu_razon_social = fields.Char(string="Razón Social")
    
    verifactu_active = fields.Boolean(string="Active Veri*Factu")
        
    verifactu_p12_file = fields.Binary(string="Certificado .p12", attachment = True, copy = False, ondelete = 'set null',  help='Contenido del certificado p12')
    verifactu_p12_filename  = fields.Char(string="certificado .p12")

    verifactu_p12_password = fields.Char(
        string="Contraseña .p12",
        help="Contraseña del fichero .p12. Dejar en blanco si no tiene."
    )
    verifactu_operation = fields.Char(
        string="Operaciones",
        help="Descripción de las operaciones incuidas en las facturas (opcional)"
    )
    
    @api.multi
    def vat_clean(self):
        ''' return country code and vatnumber '''
        self.ensure_one()
        country_code = self.country_id.code
        vat_number = self.vat
        vat = re.sub(r"^%s" % re.escape(country_code), "", vat_number, flags=re.IGNORECASE).strip()
        return country_code, vat

    
    @api.model
    def create(self, values):
        '''Ensure companies from spain must active veri*factu'''
        record = super(res_company, self).create(values = values)
        if record.vat[:2] == 'ES' and not record.verifactu_active:
            record.write({'verifactu_active': True})
            
    @api.multi
    def write(self, values):
        '''Ensure companies from spain must active veri*factu'''
        res = super(res_company, self).write(values = values)
        companies_to_force_verifactu_active = self.filtered(lambda c: c.vat[:2]=='ES' and not c.verifactu_active)
        if len(companies_to_force_verifactu_active):
            res = res and super(res_company, self).write({'verifactu_active': True})
        return res
    
            