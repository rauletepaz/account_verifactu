# -*- coding: utf-8 -*-

import re
import base64

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.backends import default_backend



class res_company(models.Model):
    _inherit = 'res.company'
    
    verifactu_razon_social = fields.Char(string="Razón Social")
        
    verifactu_date = fields.Date(help="Fecha a partir de la cual la compañía debe aplicar la norma Veri*factu")
    verifactu_sif = fields.Selection([('verificable','SIF verificable'),('no_verificable','SIF no verificable')], 
                                     help=_("""
* SIF verificable:    Remisión Automática a AEAT en tiempo real, 
                      el qr es verificable en la AEAT, 
                      la firma electrónica no es necesaria,
                      el registro de eventos no es necesario.
                      
* SIF no veificable:  Remisión a AEAT bajo requerimiento, 
                      el qr no es verificable en la AEAT, 
                      firma electrónica obligatoria (XAdES EPES),
                      el registro interno de eventos es obligatorio.
""")
)
    verifactu_simplified_invoices = fields.Boolean(string='Simplified invoices', help='Simplified invoices like ticket of sale with no customer idenfied', default = False)

        
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
    def verificar_p12(self, p12_bytes, password):
        """
        Verifica que el archivo p12 sea correcto y la contraseña válida.
        :param p12_bytes: contenido binario del archivo (no base64)
        :param password: cadena de texto (puede ser None si sin clave)
        :return: True si es válido, False en caso contrario
        """
        try:
            p12_data = base64.b64decode(p12_bytes or b'')
            if isinstance(password, str):
                password = password.encode('utf-8')
            # Intenta decodificar el contenedor PKCS#12
            key, cert, ca_certs = pkcs12.load_key_and_certificates(
                p12_data, password, backend=default_backend()
            )
            # Debe haber al menos una clave o un certificado
            return bool(cert or key)
        except Exception as e:
            # Log opcional: _logger.warning('Error validando p12: %s', e)
            return False
    
    @api.onchange('verifactu_date','vat','verifactu_simplified_invoices')
    def onchange_verifactu_date(self):
        verifactu_simplified_invoices = self.sudo().env['ir.config_parameter'].get_param('account_verifactu.verifactu_simplified_invoices')
        verifactu_runing = self.sudo().env['ir.config_parameter'].get_param('account_verifactu.verifactu_runing')
        if self.vat[:2] == 'ES' and not self.verifactu_date:
            self.verifactu_date = '2026-01-01'
            self.verifactu_sif = 'verificable'
        if self.verifactu_date and not self.verifactu_sif:
            self.verifactu_sif = 'verificable'
        if self.verifactu_date and self.verifactu_simplified_invoices and not verifactu_simplified_invoices:
            self.verifactu_simplified_invoices = False
            return {'warning': {'title': _('NOT ALLOWED'),'message':_('Activate simplied invoices on Veri*factu configuration before use it')}}
        
            
    @api.model
    def create(self, values):
        '''Ensure companies from spain must active veri*factu'''
        if 'vat' in values and values['vat'][:2] == 'ES':
            values['verifactu_date'] = values.get('verifactu_date', '2026-01-01')
            values['verifactu_sif'] = values.get('verifactu_sif','verificable')
        if 'verifactu_date' in values:
            values['verifactu_sif'] = values.get('verifactu_sif','verificable')
        if values.get('verifactu_sif',False) == 'no_verificable':
            if not values.get('verifactu_p12_file',False) or not values.get('verifactu_p12_password',False):
                raise ValidationError(_("An electronic signature is mandatory. You need your p12 file and password"))
            if not self.verificar_p12(values['verifactu_p12_file'],values['verifactu_p12_password']):
                raise ValidationError(
                    "El archivo proporcionado no es un certificado PKCS#12 válido "
                    "o la contraseña es incorrecta."
                )    
        if 'verifactu_date' in values:
            verifactu_simplified_invoices = self.sudo().env['ir.config_parameter'].get_param('account_verifactu.verifactu_simplified_invoices')
            values['verifactu_simplified_invoices'] = values.get('verifactu_simplified_invoices',False) and verifactu_simplified_invoices
        return super(res_company, self).create(values = values)
            
    @api.multi
    def write(self, values):
        '''Ensure companies from spain must active veri*factu'''
        res = super(res_company, self).write(values)
        for company_id in self:
            correction_values = {}
            if company_id.vat[:2] == 'ES' and not company_id.verifactu_date:
                correction_values['verifactu_date'] = '2026-01-01'
            if company_id.verifactu_date or correction_values.get('verifactu_date',False):
                if not company_id.verifactu_sif:
                    correction_values['verifactu_sif'] = 'verificable'
                if company_id.verifactu_sif == 'no_verificable':
                    if not company_id.verifactu_p12_file or not company_id.verifactu_p12_password:
                        raise ValidationError(_("An electronic signature is mandatory. You need your p12 file and password. %s") % company_id.name)
                    if not self.verificar_p12(company_id.verifactu_p12_file,company_id.verifactu_p12_password):
                        raise ValidationError(_(
                            "El archivo proporcionado no es un certificado PKCS#12 válido "\
                            "o la contraseña es incorrecta."\
                            "%s") % company_id.name
                        )      
                if company_id.verifactu_simplified_invoices:
                    verifactu_simplified_invoices = self.sudo().env['ir.config_parameter'].get_param('account_verifactu.verifactu_simplified_invoices')
                    if not verifactu_simplified_invoices:
                        correction_values['verifactu_sif'] = verifactu_simplified_invoices
            if correction_values:
                res = super(res_company, self).write(correction_values)
        return res
    
            