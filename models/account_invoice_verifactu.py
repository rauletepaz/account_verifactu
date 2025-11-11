# -*- coding: utf-8 -*-
import re
import logging
import hashlib
import base64
import requests
from urllib.parse import urlencode, quote
from datetime import datetime, date


from lxml import etree
from signxml import XMLSigner, methods
from cryptography.hazmat.primitives.serialization import pkcs12
from requests_pkcs12 import post as pkcs12_post

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class AccountInvoiceVerifactu(models.Model):
    _name = "account.invoice.verifactu"

    invoice_id = fields.Many2one('account.invoice')
    number = fields.Char(related='invoice_id.move_name')
    
    verifactu_qr = fields.Binary("Veri*factu QR",
        help="QR fro veri*factu 200x200px")
    
    hash = fields.Char(size=256,
        help="Hash gerenated for sending AEAT")
    
    anterior = fields.Many2one('account.invoice.verifactu', help="Anterior register sent to AEAT to use as concatenation")
    
    type = fields.Selection([('alta','Registro de alta'),('anulation','Registro de anulación'),('event','Registro de evento')])
    
    even_type = fields.Selection(
        [('01','Inicio del funcionamiento del sistema informático como «NO VERI*FACTU».'),
        ('02','Fin del funcionamiento del sistema informático como «NO VERI*FACTU».'),
        ('03','Lanzamiento del proceso de detección de anomalías en los registros de facturación.'),
        ('04','Detección de anomalías en la integridad, inalterabilidad y trazabilidad de registros de facturación.'),
        ('05','Lanzamiento del proceso de detección de anomalías en los registros de evento.'),
        ('06','Detección de anomalías en la integridad, inalterabilidad y trazabilidad de registros de evento.'),
        ('07','Restauración de copia de seguridad, cuando ésta se gestione desde el propio sistema informático de facturación.'),
        ('08','Exportación de registros de facturación generados en un periodo.'),
        ('09','Exportación de registros de evento generados en un periodo.'),
        ('10','Registro resumen de eventos'),
        ('90','Otros tipos de eventos a registrar voluntariamente por la persona o entidad productora del sistema informático.')
        ]
        )
    
    state = fields.Selection([
          ('draft', 'No informada'),
          ('accepted', 'Aceptada'),
          ('partially_accepted', 'Parcialmente Aceptada'),
          ('rejected', 'Rechazada'),
      ], default='draft',
         help="""
         *draft (No informada): No enviada/informada a la AEAT,
         *accepted (Aceptada): Enviada/informada a la AEAT y aceptado el registro,
         *partially_accepted (Parcialmente aceptada):  Enviada/informada a la AEAT y aceptada con errores. Procede enviar ALTA por Subsanación (no anulación), corrigiendo los datos erróneos.,
         *rejected (Rechazada): Enviada/informada a la AEAT pero el registro es rechazado por errores, debe corregirse y volverse a enviar/informar
         """)
    
    state_icon = fields.Char(string=' ', compute='_compute_state_icon', store=False)
    
    sin_registro_previo = fields.Selection([('S','Si'),('N','No')], help=_("Not exist an informed invoice"))
    rechazo_previo = fields.Selection([('S','Si'),('N','No'),('X','')], help=_("Exist a rejected try"))
    subsanacion = fields.Selection([('S','Si'),('N','No')], help=_("Exist a partially accepted register"))
    
    registro_factura = fields.Text(string="Registro Factura Verifactu")
    
    signature = fields.Text(help="Firma electrónica del registro de facturación en formato Xades Enveloped.\n Namespace=http://www.w3.org/2000/09/xmldsig#", default='')
    
    request = fields.Text(help="Soap Envelope to send AEAT, including registro_factura and signature", default='')
    
    response = fields.Text(help="AEAT soap service response")
    
    response_mode = fields.Selection([
        ('xml', 'XML'),
        ('html', 'HTML'),
        ('json', 'JSON'),
        ('text', 'Texto'),
    ], string='Modo de respuesta', compute='_compute_response_mode', store=False)
    
    response_html = fields.Html(string="Respuesta (HTML)", compute='_compute_response_html', store=False)

    generation_date = fields.Char(string='Generation date ISO with TZ')
    
    date_invoice = fields.Char(string='Invoice date format DD-MM-YYYY', compute='_compute_date_invoice', store=False)
    
    send_date = fields.Datetime()
    
    @api.model
    def create(self, values):
        if 'invoice_id' in values and 'type' in values:
            invoice_id = self.env['account.invoice'].sudo().browse(values['invoice_id'])
            # Si el código qr se había generado debemos mantenerlo
            verifactu_qr = invoice_id.verifactu_qr or b'' # guardamos el código qr
            if invoice_id.exists() and (invoice_id.type in ['out_invoice','out_refund']) and invoice_id.verifactu_active:
                if invoice_id.verifactu_invoice_type in invoice_id.verifactu_allowed_type_ids:
                    if values['type'] == 'alta':
                        if invoice_id.verifactu_id and invoice_id.verifactu_id.state == 'accepted':
                            raise UserError(_('Invoice %s has alredy informed correctly') % invoice_id.move_name)
                        else:
                            res = super(AccountInvoiceVerifactu,self).create(values)
                            if res:
                                res.update_register_data()
                                if res.invoice_id.company_id.verifactu_sif == 'verificable':
                                    res.send_soap_request()
                                    if res.state in ['accepted','partially_accepted']:
                                        res.generate_qr()
                                elif res.invoice_id.company_id.verifactu_sif == 'no_verificable':
                                    res.generate_qr()
                            return res
                    elif values['type'] == 'anulation':
                        if not invoice_id.verifactu_id:
                            raise UserError(_("Invoice %s isn't informed so you can't anulate it") % invoice_id.move_name)
                        elif invoice_id.state == 'open' and invoice_id.verifactu_state not in ['accepted','partially_accepted']:
                            raise UserError(_("Open invoice %s isn't informed so you can't anulate it") % invoice_id.move_name)
                        elif invoice_id.state == 'cancel' and invoice_id.verifactu_state not in ['rejected']:
                            raise UserError(_("Canceled invoice %s is informed so you can't anulate it") % invoice_id.move_name)
                        else:
                            values['verifactu_qr'] = verifactu_qr # mantenemos el mismo qr que el de la factura sin anular
                            res = super(AccountInvoiceVerifactu,self).create(values)
                            if res:
                                res.update_register_data()
                                if res.invoice_id.company_id.verifactu_sif == 'verificable':
                                    res.send_soap_request()
                                    if res.state in ['accepted','partially_accepted']:
                                        res.generate_qr()
                                elif res.invoice_id.company_id.verifactu_sif == 'no_verificable':
                                    res.write()
                                    res.generate_qr()
                            return res
                    else:
                        # event to do
                        raise ValidationError(_("Event process to do"))
                else:
                    raise ValidationError(_('Invoice type error'))                    
            else:
                raise ValidationError(_('Just out invoices and refund for verifactua active companies should be informed'))
        else:
            raise ValidationError(_('Register type or invoice not found'))
    
    @api.model
    def compare_registers(self, reg1, reg2):
        ''' Comprueba si dos registros se generan a partir de los mismo datos de factura '''
        parser = etree.XMLParser(remove_blank_text=False) # limpia indentaciones
        # Etiquetas a ignorar
        tags = ['Subsanacion','Huella','FechaHoraHusoGenRegistro','RechazoPrevio','Encadenamiento','TipoRectificativa']
        # string de busqueda
        path = '//*[local-name()="'+'" or local-name()="'.join(tags)+'"]'
        # Limpiamos la huella y la fecha de registro para el xml1
        xml1 = etree.fromstring(reg1.encode('utf-8'), parser=parser)
        objetivos = xml1.xpath(path)
        for elem in objetivos:
            parent = elem.getparent()
            if parent is not None:
                parent.remove(elem)
        
        xml2 = etree.fromstring(reg2.encode('utf-8'), parser=parser)
        objetivos = xml2.xpath(path)
        for elem in objetivos:
            parent = elem.getparent()
            if parent is not None:
                parent.remove(elem)
        
        # comparar por C14N tras normalizar
        reg1_c14n = etree.tostring(xml1, method='c14n', exclusive=True, with_comments=False)
        reg2_c14n = etree.tostring(xml2, method='c14n', exclusive=True, with_comments=False)
        _logger.info(self.pretty_xml(reg1_c14n, xml_declaration=False))
        _logger.info(self.pretty_xml(reg2_c14n, xml_declaration=False))
        return reg1_c14n == reg2_c14n


    @api.depends('state')
    def _compute_state_icon(self):
        for rec in self:
            mapping = {
                'draft': u'●',                 # punto (gris por decoración)
                'accepted': u'✓',              # check
                'partially_accepted': u'✓',    # check
                'rejected': u'✗',              # cruz
            }
            rec.state_icon = mapping.get(rec.state, u'●')
        
    @api.depends('response')
    def _compute_response_mode(self):
        '''
        La AEAT devuelve una respuesta XML cuando la connexión y el envío se ha producido correctamente.
        En caso contrario devuelve un html 
        '''
        for rec in self:
            t = (rec.response or '').lstrip()
            low = t[:200].lower()
            mode = 'text'
            if t.startswith('{') or t.startswith('['):
                mode = 'json'
            elif t.startswith('<'):
                if low.startswith('<!doctype html') or '<html' in low:
                    mode = 'html'
                else:
                    mode = 'xml'
            rec.response_mode = mode

    @api.depends('response', 'response_mode')
    def _compute_response_html(self):
        for rec in self:
            rec.response_html = rec.response if rec.response_mode == 'html' else False
            
    @api.depends('invoice_id.date_invoice')
    def _compute_date_invoice(self):
        for rec in self:
            if rec.invoice_id.date_invoice:
                rec.date_invoice = datetime.strptime(
                    rec.invoice_id.date_invoice, "%Y-%m-%d"
                ).strftime("%d-%m-%Y")
            else:
                rec.fecha_ddmmyyyy = ""

    @api.model
    def pretty_xml(self, xml_str, encoding='UTF-8', xml_declaration=True):
        '''
        Permite visualizar la respusta de forma legible
        '''
        if xml_str in (None, b'', u''):
            return xml_str

        is_bytes = isinstance(xml_str, (bytes, bytearray))
        data = xml_str if is_bytes else xml_str.encode('utf-8')

        try:
            # Forzar fallo en XML inválido (sin recover) y limpiar espacios
            parser = etree.XMLParser(remove_blank_text=True, recover=False)
            root = etree.fromstring(data, parser=parser)
        except Exception as e:
            # Log y devolver tal cual sin romper
            _logger.warning("pretty_xml: contenido no es XML válido: %s", e)
            return xml_str

        # Si entraron bytes, devolver bytes con la codificación solicitada
        return etree.tostring(
                root,
                pretty_print=True,
                encoding=(encoding if is_bytes else 'unicode'),
                xml_declaration=(xml_declaration if is_bytes else False),
            )
            
    @api.multi
    def verifactu_endpoint(self):
        '''
        Depende de la configuración del módulo y de la configiración de la compañia.
        El endpoint varia según se trate de sofware verificable o no
        y si estamos en modo producción o pruebas
        '''
        self.ensure_one()
        runing_method = self.sudo().env['ir.config_parameter'].get_param('account_verifactu.verifactu_runing_method')
        sif_verificable = self.invoice_id.company_id.verifactu_sif
        endpoint = False
        if runing_method == 'production':
            if sif_verificable == 'verificable':
                endpoint = self.sudo().env['ir.config_parameter'].get_param('account_verifactu.verifactu_endpoint_produccion_verificable')
            else:
                endpoint = self.sudo().env['ir.config_parameter'].get_param('account_verifactu.verifactu_endpoint_produccion_no_verificable')
        else:
            if sif_verificable == 'verificable':
                endpoint = self.sudo().env['ir.config_parameter'].get_param('account_verifactu.verifactu_endpoint_no_produccion_verificable')
            else:
                endpoint = self.sudo().env['ir.config_parameter'].get_param('account_verifactu.verifactu_endpoint_no_produccion_no_verificable')
        return endpoint
    
    @api.multi
    def generate_qr(self):
        '''
        Genera el QR y lo asocia al registro
        '''
        

        report = self.env['ir.actions.report']
        for vf in self:
            # normalize NIF to not include country sympbol
            country_code = vf.invoice_id.company_id.country_id.code
            vat_number = vf.invoice_id.company_id.vat
            vat = re.sub(r"^%s" % re.escape(country_code), "", vat_number, flags=re.IGNORECASE).strip()
            date = datetime.strptime(vf.invoice_id.date_invoice, "%Y-%m-%d").strftime("%d-%m-%Y")
            amount = "{:.2f}".format(vf.invoice_id.amount_total)
            number = vf.invoice_id.move_name
            params = {
                'nif': vat,
                'numserie': number,   # el '/' se codificará a %2F
                'fecha': date,         # DD-MM-AAAA
                'importe': amount,             # punto decimal
            }
            # Codifica SOLO valores de parámetros (mantén ?, &, = sin codificar)
            endpoint = self.verifactu_endpoint().replace('/ws/SistemaFacturacion/VerifactuSOAP','/ValidarQR').replace('/ws/SistemaFacturacion/RequerimientoSOAP','ValidarQRNoVerifactu').replace('www1','www2')
            value = endpoint + '?' + urlencode(params, quote_via=quote, safe='')
            # Genera el QR sin volver a codificar la URL completa
            png = report.barcode('QR', value, width=200, height=200, humanreadable=0)
            # genera PNG (bytes) y guarda en binario (base64-encoded BYTES, no str)
            vf.verifactu_qr = base64.b64encode(png)  # NO hagas str(...)
        # importante: recargar la vista para ver la imagen recién escrita
        return {'type': 'ir.actions.client', 'tag': 'reload'}   
    
    @api.multi
    def _build_signature_tag_from_p12(self):
        """
        Devuelve SOLO el tag <ds:Signature>...</ds:Signature> (XMLDSig Enveloped),
        para que puedas insertarlo dentro del XML del registro.

        :param xml_to_sign: str (XML del registro SIN firma)
        :param p12_path:    ruta absoluta al .p12
        :param p12_password: contraseña del .p12 ('' si no tiene)
        :return: str con el elemento <ds:Signature> serializado en UTF-8
        """
        self.ensure_one()
        # 1) Parsear el XML a firmar
        xml_to_sign = self.registro_factura
        try:
            if isinstance(xml_to_sign, (bytes, bytearray)):
                root = etree.fromstring(xml_to_sign)
            else:
                root = etree.fromstring(xml_to_sign.encode("utf-8"))
        except Exception as e:
            _logger.exception("XML inválido para firmar")
            raise UserError(_("El XML a firmar no es válido: %s") % e)
        
        # 1.b) Recuperar compañía y validar que tiene certificado en campos Binary
        company = self.invoice_id.company_id if self.invoice_id else False
        if not (company and company.verifactu_date):
            raise UserError(_("Esta compañía no está habilitada para Verifactu."))
    
        if not company.verifactu_p12_file:
            raise UserError(_("No se encontró el contenido del certificado .p12 en la compañía."))
    
        p12_password = (company.verifactu_p12_password or "").strip()
    
        # 2) Cargar clave y certificado desde PKCS#12 (desde Binary base64)
        try:
            p12_data = base64.b64decode(company.verifactu_p12_file)
        except Exception as e:
            _logger.exception("Error decodificando el .p12 (base64)")
            raise UserError(_("El contenido base64 del .p12 es inválido: %s") % e)
    
        try:
            try:
                # cryptography >= 3.4 (no necesita backend)
                private_key, cert, additional_certs = pkcs12.load_key_and_certificates(
                p12_data,
                p12_password.encode("utf-8") if p12_password else None
                )
            except TypeError:
                # cryptography 2.x (requiere backend)
                from cryptography.hazmat.backends import default_backend
                private_key, cert, additional_certs = pkcs12.load_key_and_certificates(
                p12_data,
                p12_password.encode("utf-8") if p12_password else None,
                backend=default_backend()
                )
            if private_key is None or cert is None:
                raise ValueError("El .p12 no contiene clave y/o certificado.")
        except Exception as e:
            _logger.exception("Error cargando .p12 desde Binary")
            raise UserError(_("No se pudo cargar el .p12: %s") % e)


        # 3) Preparar firmante XMLDSig Enveloped (RSA-SHA256, digest SHA256, C14N 1.0)
        signer = XMLSigner(
            method=methods.enveloped,
            signature_algorithm="rsa-sha256",
            digest_algorithm="sha256",
            c14n_algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315",
        )

        # 4) Firmar el documento (inserta <ds:Signature> dentro del root)
        try:
            # reference_uri=None => referencia al root (enveloped signature)
            #Firmar: usar cert_chain en lugar de cert (evita el TypeError)
            chain = [cert] + (additional_certs or [])
            signed_root = signer.sign(
                root,
                key=private_key,
                cert=chain,                     # << clave: iterable con el cert principal y cadena
                key_name=None,                  # puedes poner un KeyName si AEAT lo pide
                always_add_key_value=True       # añade <ds:KeyValue> (útil para interoperabilidad)
            )
        except TypeError:
            # Fallback para versiones que esperan bytes DER en lugar de objetos
            from cryptography.hazmat.primitives import serialization
            chain_der = [c.public_bytes(serialization.Encoding.DER) for c in [cert] + (additional_certs or [])]
            signed_root = signer.sign(
                root,
                key=private_key,
                cert_chain=chain_der, 
                key_name=None,
                always_add_key_value=True
            )
        except Exception as e:
            _logger.exception("Error firmando XML")
            raise UserError(_("Fallo al firmar el XML: %s") % e)

        # 5) Extraer SOLO el elemento <ds:Signature> y devolverlo como string
        DSIG_NS = "http://www.w3.org/2000/09/xmldsig#"
        sig_el = signed_root.find(".//{%s}Signature" % DSIG_NS)
        if sig_el is None:
            raise UserError(_("No se pudo localizar el elemento <Signature> en la firma generada."))

        return etree.tostring(sig_el, pretty_print=True, encoding="utf-8").decode("utf-8")
        
    @api.multi    
    def generate_hash(self):
        self.ensure_one()
        country_code = self.invoice_id.company_id.country_id.code
        vat_number = self.invoice_id.company_id.vat
        vat = re.sub(r"^%s" % re.escape(country_code), "", vat_number, flags=re.IGNORECASE).strip()
        cuples = []
        chain = ''
        if self.type=='alta':
            cuples = [
                ("IDEmisorFactura", vat),
                ("NumSerieFactura", self.invoice_id.move_name.strip()),
                ("FechaExpedicionFactura", self.date_invoice.strip()),
                ("TipoFactura", self.invoice_id.verifactu_invoice_type.type),
                ("CuotaTotal", "{:.2f}".format(self.invoice_id.amount_tax  * (1 if self.invoice_id.type == 'out_invoice' else -1))),
                ("ImporteTotal", "{:.2f}".format(self.invoice_id.amount_total  * (1 if self.invoice_id.type == 'out_invoice' else -1))),
                ("Huella", (self.anterior and self.anterior.hash or "").strip()),
                ("FechaHoraHusoGenRegistro", self.generation_date),
            ]
        elif self.type=='anulation':
            cuples = [
                ("IDEmisorFacturaAnulada", vat),
                ("NumSerieFacturaAnulada", self.invoice_id.move_name.strip()),
                ("FechaExpedicionFacturaAnulada", self.date_invoice.strip()),
                ("Huella", (self.anterior and self.anterior.hash or "").strip()),
                ("FechaHoraHusoGenRegistro", self.generation_date),
            ]            
        elif self.type=='event':
            cuples = [
                ("NIF", vat),
                ("IdSistemaInformatico", 'OD'),
                ("Version", '11.0.0'),
                ("NumeroInstalacion", str(self.invoice_id.company_id.id)),
                ("NIF", vat),
                ("TipoEvento", self.even_type),
                ("HuellaEvento", (self.anterior and self.anterior.hash or "").strip()),
                ("FechaHoraHusoGenEvento", self.generation_date),
            ]            
        if cuples:
            chain = "&".join("{}={}".format(k, v) for k, v in cuples)
            self.hash = hashlib.sha256(chain.encode("utf-8")).hexdigest().upper()
            _logger.info('Hass: %s calculated for chain %s' % (self.hash, chain))
        return chain
    
    @api.multi
    def update_register_data(self):
        self.ensure_one()
    
        # === 0) Tiempos para cadena/encadenamiento now() in ISO format===
        self.generation_date = (lambda s: s[:-2] + ':' + s[-2:])(
            fields.Datetime.context_timestamp(self, datetime.utcnow()).strftime('%Y-%m-%dT%H:%M:%S%z')
        )
        domain = [('id', '!=', self.id)] if not isinstance(self.id, models.NewId) else []
        domain += [('state', '!=', 'draft'),('invoice_id.company_id', '=', self.invoice_id.company_id.id),]
        domain += [('type','=','event')] if self.type == 'event' else [('type','!=','event')]
            
        prev_any = self.search(domain + [('invoice_id', '=', self.invoice_id.id),], order='send_date desc, generation_date desc, id desc', limit=1)
        prev_rejected = bool(prev_any and prev_any.state == 'rejected')
        prev_in_aeat = self.search(domain + [('invoice_id', '=', self.invoice_id.id),('state', 'in', ['accepted', 'partially_accepted']),], limit=1).exists()
        # El encadenado debe sólo con registros aceptados o partcialmente aceptados
        self.anterior = self.search(domain + [('state', 'in', ['accepted', 'partially_accepted']),], order="send_date desc, generation_date desc, id desc", limit=1)
    
        # === 1) Ramas por tipo ===
        if self.type == 'alta':
            self.subsanacion = 'S' if (prev_in_aeat or prev_rejected) else 'N'
            self.sin_registro_previo = 'N' if prev_in_aeat else 'S'
            if self.subsanacion == 'S' and self.sin_registro_previo == 'S':
                self.rechazo_previo = 'X'
            else:
                self.rechazo_previo = 'S' if self.subsanacion == 'S' and prev_rejected else 'N'
        elif self.type == 'anulation':
            self.subsanacion = 'S' if prev_rejected else 'N'
            self.sin_registro_previo = 'N' if prev_in_aeat else 'S'
            self.rechazo_previo = 'S' if prev_rejected else 'N'
        elif self.type == 'event':
            self.sin_registro_previo = self.rechazo_previo = self.subsanacion = ''
    
        # === 2) Huella (dependiente de type)
        self.generate_hash()
        self.generate_register()
        # === 3) Firma y regeneración XML en No-Verificable ===
        if self.invoice_id.company_id.verifactu_sif == 'no_verificable':
            self.signature = self._build_signature_tag_from_p12()
            if not self.signature:
                raise UserError(_("Unverificable software: se requiere p12 en la compañía."))
            # Re-render con <ds:Signature/> embebida
            self.generate_register()
    
        return True


    @api.multi
    def generate_register(self):
        """Renderiza el template QWeb y guarda el resultado en RegistroFactura."""
        self.ensure_one()
        if not self.invoice_id or not self.invoice_id.verifactu_active:
            raise UserError(_("There isn't any information to send"))
        
        default_template = {
                'alta': 'account_verifactu.RegistroAlta',
                'anulation': 'account_verifactu.RegistroAnulacion',
                'event': 'account_verifactu.RegistroEvento',
                }[self.type]
        template_xml_id = self._context.get('template_xml_id',default_template)
        if not template_xml_id:
            return False

        self.ensure_one()
        qweb = self.env['ir.qweb']
        values = {
                'o': self,   # para ${object...}
                'env': self.env, # útil si lo usas en expresiones
                '_': _,
            }
        rendered = qweb.render(template_xml_id, values) 
        if isinstance(rendered, (bytes, bytearray)):
            rendered = rendered.decode('utf-8')
        # En Odoo 11, _render puede devolver bytes. Normalizamos a unicode.
        self.registro_factura = self.pretty_xml(rendered,xml_declaration=False)
        return True
    
    @api.multi
    def generate_soap_envelope(self):
        """Renderiza el template QWeb y devueve el resultado."""
        self.ensure_one()
        if not self.registro_factura:
            raise UserError(_("No existe el XML de RegistroFactura."))
        try:
            qweb = self.env['ir.qweb']
            template_xml_id = 'account_verifactu.soap_request'
            values = {
                    'o': self,   # para ${object...}
                    'env': self.env, # útil si lo usas en expresiones
                }
            request = qweb.render(template_xml_id, values)
            # En Odoo 11, _render puede devolver bytes. Normalizamos a unicode.
            self.request = self.pretty_xml(request,xml_declaration=True)
        except:
            raise UserError(_("Could'nt be posible to prepare sopa envelope"))
        return True

    def send_soap_request(self):
        self.ensure_one()
        if not self.invoice_id or not self.invoice_id.verifactu_active or not self.registro_factura:
            raise UserError(_("There isn't any information to send"))
        self.generate_soap_envelope()
        return self.send_aeat()
    
    def send_aeat(self):
        self.ensure_one()
        # Preparar headers, endpoint
        headers = {
            'Content-Type': 'text/xml; charset=utf-8',
        }
        soap_action = self.sudo().env['ir.config_parameter'].get_param('account_verifactu.soap_action') or ''
        if soap_action:
            headers['SOAPAction'] = soap_action
        verifactu_endpoint = self.verifactu_endpoint()

        # Verificación SSL configurable (por defecto True)
        ssl_verify_param = self.sudo().env['ir.config_parameter'].get_param('account_verifactu.ssl_verify', 'True')
        verify_ssl = (str(ssl_verify_param).lower() != 'false')

        if not verifactu_endpoint:
            self.state = 'rejected'
            raise UserError(_("No hay endpoint configurado para Veri*factu."))
        
        try:
            # La administración exige una conexión segurra de punto a punto
            p12_data = base64.b64decode(self.invoice_id.company_id.verifactu_p12_file or b'')
            p12_password = (self.invoice_id.company_id.verifactu_p12_password or '').strip()
            resp = pkcs12_post(
                verifactu_endpoint,
                data=(self.request or '').encode('utf-8'),
                headers=headers,
                pkcs12_data=p12_data,
                pkcs12_password=p12_password,
                timeout=(15, 90),
                verify=verify_ssl,      # cadena de confianza (True o ruta a CA)
            )
            self.response = self.pretty_xml(resp.text, encoding='UTF-8', xml_declaration=True) or ''
            _logger.infor('AEAT request: %s' % self.request)
            _logger.info('AEAT response: %s' % self.response)
            # En caso de respuesta de tipo html no aseguramos de mantener la codificación
            if self.response_mode == 'html':
                raw = resp.content  # bytes
                enc = 'utf-8'
                # intenta detectar por cabecera o meta
                ct = (resp.headers.get('Content-Type') or '').lower()
                if 'charset=' in ct:
                    enc = ct.split('charset=')[-1].split(';')[0].strip()
                else:
                    # mira <meta charset="...">
                    m = re.search(br'<meta[^>]+charset=["\']?([a-z0-9\-]+)', raw, re.I)
                    if m:
                        enc = m.group(1).decode('ascii', 'ignore')
                html_text = raw.decode(enc, errors='replace')
                if '<base ' not in html_text.lower():
                    html_text = html_text.replace('<head>', '<head><base href="https://sede.agenciatributaria.gob.es/">', 1)
                self.response = html_text
            resp.raise_for_status()
        except Exception as e:
            _logger.exception('Error de conexión enviando a AEAT')
            # Estado rechazado por fallo de transporte
            self.state = 'rejected'
            # Intentamos dejar trazas útiles al usuario
            raise UserError(_("Error de conexión con AEAT: %s") % e)

        # Interpretar la respuesta SOAP/XML para fijar el estado
        try:
            if isinstance(resp.content, (bytes, bytearray)):
                data = resp.content
            else:
                data = resp.content.encode('utf-8')

            root = etree.fromstring(data)

            def first_text(xpaths):
                for xp in xpaths:
                    el = root.find(xp)
                    if el is not None and (el.text or '').strip():
                        return el.text.strip()
                return ''

            # Posibles ubicaciones/campos según documentación/respuestas AEAT
            estado = first_text([
                './/{*}EstadoEnvio',
                './/{*}Estado',
                './/{*}Resultado',
                './/{*}CodigoResultado',
                './/{*}CodigoRespuesta',
                './/{*}resultCode',
            ])

            # Buscar errores
            errores_nodes = (
                root.findall('.//{*}Errores/{*}Error') or
                root.findall('.//{*}ListaErrores/{*}Error') or
                root.findall('.//{*}Errores')
            )
            hay_errores = False
            if errores_nodes:
                for e in errores_nodes:
                    cod = (e.findtext('.//{*}Codigo') or e.findtext('.//{*}codigoError') or e.findtext('.//{*}CodigoError') or '').strip()
                    if cod:
                        hay_errores = True
                        break

            estado_l = (estado or '').lower()
            # Decisión del estado
            if (
                'parcial' in estado_l or
                'con error' in estado_l or
                'conerro' in estado_l or
                (hay_errores and ('acept' in estado_l or estado_l in ('00', '0', 'ok')))
            ):
                self.state = 'partially_accepted'
            elif (
                (estado_l in ('correcto', 'ok', '00', '0')) or ('acept' in estado_l and not hay_errores)
            ):
                self.state = 'accepted'
            else:
                self.state = 'rejected'

        except Exception as e:
            _logger.exception('No se pudo parsear la respuesta SOAP de AEAT')
            self.state = 'rejected'
            return {'type': 'ir.actions.client', 'tag': 'reload'}

        return self.write({'send_date': fields.Datetime.now()})
        
    
    def action_send_bulk(self):
        """Enviar registros en bloque (histórico)"""
        # Aquí tu lógica; por ahora, solo mensaje
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': "Acción no disponible",
                'message': "Se pidieron %s registros." % len(self),
                'sticky': False,  # True = notificación persistente hasta que el usuario la cierre
                'type': 'success',  # success / warning / danger
            }
        }
