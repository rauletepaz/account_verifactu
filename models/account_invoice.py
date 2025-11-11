# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _, registry, SUPERUSER_ID
from odoo.tools import float_is_zero,float_compare
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

_DEFAULT_VERIFACTU_INVOICE_TYPE = {'in_invoice': None, 'in_refund': None, 'out_invoice': 'F1', 'out_refund': 'R4'}

# ---------- Lógica de decisión centralizada ----------
''' REGLAS DE OBLIGADO CUMPLIMIENTO (NO REVISADO)
         - verifactu_replaced_invoice tiene por dominio [('type', 'in', ['out_invoice']),('state','in',['open','paid'])]
         - Facturas de compras:
            type es 'in_invoice' o 'in_refund' 
            entonces verifactu_invoice_type y verifactu_replaced_invoice deben permanecer vacíos
         
         - Facturas rectificativas de facturas ordinarias:
            verifactu_replaced_invoice existe y
            verifactu_replaced_invoice.partner_id existe 
            entonces type debe ser 'out_refund', partner_id debe ser verifactu_replaced_invoice.partner_id y verifactu_invoice_type debe ser 'R1' por defecto pero admite 'R2','R3' y 'R4'
        
         - Factura rectificativa de facturas simplificadas:
            verifactu_replaced_invoice existe y
            verifactu_replaced_invoice.partner_id no existe y
            partner_id no existe
            entonces type debe ser 'out_refund' y verifactu_invoice_type debe ser 'R5'
        
         - Factura de sustitución de factura simplificadas:
            verifactu_replaced_invoice existe y
            verifactu_replaced_invoice.partner_id no existe y
            partner_id existe
            entonces type debe ser 'replace' y verifactu_invoice_type debe ser 'F3'
        
         - Factura ordinaria: 
            verifactu_replaced_invoice no existe y
            partner_id existe y
            type es 'out_invoice'
            entonces verifactu_invoice_type debe ser 'F1'
        
         - Abono ordinario: 
            verifactu_replaced_invoice no existe y
            partner_id existe y
            type es 'out_refund'
            entonces verifactu_invoice_type debe ser 'R1' por defecto pero admite 'R2','R3' y 'R4'
        
         - Factura simplificada: 
            verifactu_replaced_invoice no existe y
            partner_id no existe y
            entonces type debe ser 'out_invoice' y verifactu_invoice_type debe ser 'F2'         

'''


class AccountInvoice(models.Model):
    _inherit = "account.invoice"
    
    verifactu_ids = fields.One2many(comodel_name = 'account.invoice.verifactu', inverse_name = 'invoice_id')
    verifactu_id = fields.Many2one(comodel_name = 'account.invoice.verifactu', compute='_get_verifactu_id')
    verifactu_qr = fields.Binary(related='verifactu_id.verifactu_qr')
    verifactu_state = fields.Selection(related='verifactu_id.state')
    verifactu_send_date = fields.Datetime(related='verifactu_id.send_date')
    verifactu_active = fields.Boolean(compute='_get_verifactu_active')
        
    # 1) Solo se puede seleccionar como "replaced" una factura de cliente (out_invoice)
    verifactu_replaced_invoice = fields.Many2one(
        comodel_name='account.invoice',
        domain=[('type', 'in', ['out_invoice']),('state','in',['open','paid'])],
        string='Replaced Invoice',
        help="""
        Cuando se trata de una factura rectificatiiva, este campo hace referencia a la factura rectificada.
        """
    )
    
    verifactu_allowed_type_ids = fields.Many2many(compute = "_get_verifactu_allowed_type_ids", comodel_name='account.invoice.verifactu.type')
    
    verifactu_invoice_type = fields.Many2one(string='Veri*Factu Type', comodel_name='account.invoice.verifactu.type',
                                            help="""Claves F1–F2 (qué significan)
    F1 — Factura ordinaria (completa)
        Es la factura “normal” con destinatario identificado.

    F2 — Factura sin identificación del destinatario Art. 4 y 7 RD 1619/2012
        Es la “simplificada” sin datos del cliente (tickets).

    F3 — Factura de sustitución (p. ej., canje de simplificada por completa) Art. 7.2 RD 1619/2012 y art. 13 RD 1007/2023
        Se usa para sustituir otra/s factura/s (típico: canje de una F2 por una completa con datos del cliente).
        Debe llevar Destinatarios (porque ya identificas al cliente).
    
Claves R1–R5 (qué significan)
    
    R1 – Rectificativa por “error fundado en derecho”. Aart. 80.Uno LIVA
        -Errores en la apliacción del regimén (Exportación, Intracomunitario, exento, inversión del sujeto pasivo, etc)
        -Errores en el cálculo o aplicación de la cuota.
    
    R2 – Rectificativa por concurso de acreedores (art. 80.Tres LIVA).
        Se usa para reducir la base/cuota cuando el destinatario entra en concurso y se cumplen los requisitos de modificación de la base. 
    
    R3 – Rectificativa por créditos incobrables (art. 80.Cuatro LIVA).
        Aplica cuando la deuda es incobrable y procede la modificación de la base. 
    
    R4 – Rectificativa “resto de supuestos”. Art. 80.Dos LIVA supuestos:
        -Error en la identificación del emisor o receptor.
        -Descuentos y bonificaciones posteriores.
        -Devolución de material.
        -Reducción de la base imponible por devolución total o parcial de bienes.    
        -Devolución de envases, embalajes o mercancías.
        -Compensación por calidad, retrasos o penalizaciones comerciales.
        -Reducción de la contraprestación pactada.    
        -Otras causas de modificación de la contraprestación.
    
    R5 – Rectificativa de “factura simplificada”.
        Es la clave específica cuando lo que se rectifica es una factura simplificada (ticket/factura simplificada). 
    """
)
            
    @api.multi
    def action_account_invoice_payment(self):
        return self.env.ref('account.action_account_invoice_payment')
    
    @api.multi
    def action_account_invoice_refund(self):
        self.ensure_one()
        if self.verifactu_active:
            if self.verifactu_id and self.state == 'open' and self.verifactu_state in ['accepted','partially_accepted']:
                action = self.env.ref('account_verifactu.action_account_invoice_verifactu_refund').read()[0]
            else:
                raise ValidationError(_('Invoice must be open and informed correctly to AEAT in order to refund'))
        else:
            action = self.env.ref('account.action_account_invoice_refund').read()[0]
        action['context'] = dict(self._context)
        action['context'].update({'active_id': self.id, 'active_model': self._name})
        return action
    
    @api.depends('date_invoice','company_id.verifactu_date')
    def _get_verifactu_active(self):
        for f in self:
            f.verifactu_active = f.company_id.verifactu_date and f.date_invoice and bool(f.date_invoice >= f.company_id.verifactu_date)

    @api.depends('verifactu_ids', 'verifactu_ids.send_date', 'verifactu_ids.state')
    def _get_verifactu_id(self):
        '''
        El objetivo de este campo es determinar el estado del registro de factura.
        Puede haber varios registros informados para la misma factura (rechazados, aceptados con errores, anulación, rectificación)
        Esta función hace que el campo calculado verifactu_id apunte a:
            - Si el registro ha sido registrado con éxito en la AEAT como aceptado, parcialmente o anulado apunta a él (ignora los rechazos)
            - En caso contrario si existe algún rechazo, apunta al último rechazo
            - Si no existe ningún registro informado será False

        '''
        invoices_ids = self.filtered(lambda r: r.id)
        if not invoices_ids:
            self.write({'verifactu_id': False})
            return
        child = self.env['account.invoice.verifactu']
        query_including_rejected = """
                SELECT DISTINCT ON (invoice_id) id, invoice_id
                FROM account_invoice_verifactu
                WHERE invoice_id = ANY(%s)
                  AND state in ('accepted','partially_accepted','rejected')
                ORDER BY invoice_id, send_date DESC NULLS LAST, id DESC
            """
        self.env.cr.execute(query_including_rejected, [invoices_ids.ids])
        # Mapea invoice_id -> verifactu_id
        children_including_rejected_map = {invoice_id: child.browse(child_id) for child_id, invoice_id in self.env.cr.fetchall()}
    
        query_accepted = """
                SELECT DISTINCT ON (invoice_id) id, invoice_id
                FROM account_invoice_verifactu
                WHERE invoice_id = ANY(%s)
                  AND state in ('accepted','partially_accepted')
                ORDER BY invoice_id, send_date DESC NULLS LAST, id DESC
            """
            
        self.env.cr.execute(query_accepted, [invoices_ids.ids])

        children_map = {invoice_id: child.browse(child_id) for child_id, invoice_id in self.env.cr.fetchall()}
        
        for invoice_id in invoices_ids:
            if children_map.get(invoice_id.id, False) and children_map.get(invoice_id.id, False).exists():
                invoice_id.verifactu_id = children_map.get(invoice_id.id, False)
            elif children_including_rejected_map.get(invoice_id.id, False) and children_including_rejected_map.get(invoice_id.id, False).exists():
                invoice_id.verifactu_id = children_including_rejected_map.get(invoice_id.id, False)
            else:
                invoice_id.verifactu_id = False
                
    def create_account_incoice_verifactu(self, values):
        """Crea account.invoice.verifactu en un cursor independiente + commit."""
        self.ensure_one()
        dbname = self.env.cr.dbname
        with api.Environment.manage():
            with registry(dbname).cursor() as cr2:
                env2 = api.Environment(cr2, SUPERUSER_ID, dict(self.env.context or {}))
                verifactu_id = env2['account.invoice.verifactu'].sudo().create(values) 
                cr2.commit()
                return verifactu_id
            
    @api.multi
    def action_invoice_inform(self):
        # lots of duplicate calls to action_invoice_open, so we remove those already open
        self.ensure_one()
        if self.verifactu_state != 'partially_accepted' and self.state != 'draft':
            raise UserError(_("Invoice must be in draft state in order to validate it."))

        if float_compare(self.amount_total, 0.0, precision_rounding=self.currency_id.rounding) == -1:
            raise UserError(_("You cannot validate an invoice with a negative total amount. You should create a credit note instead."))
        
        if self.state == 'draft':
            self.action_date_assign()
            self.action_move_create()

        if self.type in ['out_invoice','out_refund'] and self.verifactu_active and not float_is_zero(self.amount_total, precision_rounding = self.currency_id.rounding):
            verifactu_id = self.create_account_incoice_verifactu({'invoice_id': self.id, 'type': 'alta'})  
                
        if self.verifactu_state in ['accepted','partially_accepted'] and self.state == 'draft':
            res = super(AccountInvoice, self).invoice_validate()
        elif self.state == 'draft':
            move_id = self.move_id
            self.move_id = False
            move_id.button_cancel()
            res = move_id.unlink()  
        else:
            return True           
        return res        
    
    @api.multi
    def _decide_values(self, vals_snapshot=None):
        """
        Devuelve un dict con los valores corregidos/recomendados para:
        - type
        - partner_id (solo en el caso de 'replaced'→F3 y 'out_refund' con R1..R4 desde verifactu_replaced_invoice)
        - verifactu_invoice_type
        
        según las reglas pedidas.
        """
        self.ensure_one()
        # Tomamos valores "en vivo" del record (o un snapshot propuesto por create/write)
        t = (vals_snapshot or {}).get('type', self.type)
        partner_id = (vals_snapshot or {}).get('partner_id', self.partner_id.id if self.partner_id else False)
        rep = self.verifactu_replaced_invoice  # M2O ya resuelto

        result = {'allowed': []}
        has_partner = bool(partner_id)
        has_rep = bool(rep)
        rep_has_partner = bool(rep.partner_id) if has_rep else False

        # Regla 1: si type es compra (in_invoice/in_refund) => dejar vacío verifactu & replaced
        if t in ('in_invoice', 'in_refund'):
            result.update({
                'verifactu_invoice_type': False,
                'verifactu_replaced_invoice': False, 
            })
            # No forzamos nada más
            return result

        # A partir de aquí: ámbito de ventas (out_invoice/out_refund/replaced/None)
        verifactu_invoice_type_ids = self.env['account.invoice.verifactu.type'].search([])
        verifactu_invoice_type_dict = {t.type: t for t in verifactu_invoice_type_ids}
        if has_rep:
            # 3) verifactu_replaced_invoice existe y verifactu_replaced_invoice.partner_id existe
            if rep_has_partner:
                # ⇒ debe ser out_refund; partner_id = verifactu_replaced_invoice.partner_id
                result['type'] = 'out_refund'
                if (not partner_id) or (partner_id != rep.partner_id.id):
                    result['partner_id'] = rep.partner_id.id
                # verifactu: R4 por defecto pero admite R1/R2/R3/R4
                if self.verifactu_invoice_type.type not in ('R1', 'R2', 'R3', 'R4'):
                    result['verifactu_invoice_type'] = verifactu_invoice_type_dict.get('R4',False)
                result['allowed'] = ['R1', 'R2', 'R3', 'R4']
                return result

            # 4) verifactu_replaced_invoice existe y rep.partner_id NO existe y partner_id NO existe
            if not rep_has_partner and not has_partner:
                result['type'] = 'out_refund'
                result['verifactu_invoice_type'] = verifactu_invoice_type_dict.get('R5',False)
                result['allowed'] = ['R5']
                return result

            # 5) verifactu_replaced_invoice existe y rep.partner_id NO existe y partner_id SÍ existe
            if not rep_has_partner and has_partner:
                # ⇒ es un canje/sustitución: F3
                result['type'] = 'replaced'  # <- si querías 'replace', cámbialo aquí y en selection_add
                result['verifactu_invoice_type'] = verifactu_invoice_type_dict.get('F3',False)
                result['allowed'] = ['F3']
                return result

        # Sin verifactu_replaced_invoice
        if not has_rep and has_partner:
            # 6) partner existe, type = out_invoice ⇒ F1
            if t == 'out_invoice':
                result['verifactu_invoice_type'] = verifactu_invoice_type_dict.get('F1',False)
                result['allowed'] = ['F1']
                return result

            # 7) partner existe, type = out_refund ⇒ R4 por defecto (admite R1/R2/R3/R4)
            if t == 'out_refund':
                if self.verifactu_invoice_type.type not in ('R1', 'R2', 'R3', 'R4'):
                    result['verifactu_invoice_type'] = verifactu_invoice_type_dict.get('R4',False)
                result['allowed'] = ['R1', 'R2', 'R3', 'R4']
                return result

        # 8) verifactu_replaced_invoice NO y partner NO ⇒ type = out_invoice y F2
        if not has_rep and not has_partner:
            result['type'] = 'out_invoice'
            result['verifactu_invoice_type'] = verifactu_invoice_type_dict.get('F2',False)
            result['allowed'] = ['F2']
            return result

        # Si ninguna regla aplicó (raro), no toques nada
        return result


    @api.depends('type', 'partner_id', 'verifactu_replaced_invoice')
    def _get_verifactu_allowed_type_ids(self):
        verifactu_allowed_type_ids = self.env['account.invoice.verifactu.type']
        for inv in self:
            updates = inv._decide_values()
            allowed = updates.pop('allowed')
            # Aplicamos cambios
            inv.verifactu_allowed_type_ids = verifactu_allowed_type_ids.search([('type','in',allowed)])
        
    # ---------- Onchange: aplica automáticamente en el formulario ----------
    @api.onchange('type', 'partner_id', 'verifactu_replaced_invoice')
    def _onchange_verifactu_rules(self):
        # Dominio dinámico de verifactu_invoice_type según el caso (opcional, UI)
        domains = {}
        for inv in self:
            updates = inv._decide_values()
            domains[inv.id] = updates.pop('allowed')
            if not updates:
                continue
            # Aplicamos cambios
            inv.update(updates) 
        # QWeb/onchange devuelve un único dominio; aplico el del primer registro del batch
        if self:
            first_allowed = domains[self[0].id]
            return {'domain': {'verifactu_invoice_type': [('value', 'in', first_allowed)]} if first_allowed else {}}

    # ---------- Validación dura en servidor ----------
    @api.constrains('type', 'partner_id', 'verifactu_replaced_invoice', 'verifactu_invoice_type')
    def _check_verifactu_rules(self):
        for inv in self:
            # Regla 1: compras -> ambos vacíos
            if inv.type in ('in_invoice', 'in_refund'):
                if inv.verifactu_invoice_type and inv.verifactu_invoice_type.type or inv.verifactu_replaced_invoice:
                    raise ValidationError(_("En facturas de compra (in_invoice/in_refund) "
                                            "verifactu_invoice_type y verifactu_replaced_invoice deben estar vacíos."))
                continue

            # Recalcular decisión esperada y comparar
            expected = inv._decide_values()
            expected.pop('allowed')
            # Solo comprobamos las claves con reglas explícitas
            checks = {}
            for k in ('type', 'verifactu_invoice_type'):
                if k in expected:
                    checks[k] = expected[k]

            # partner_id forzado en el caso replaced->R1..R4
            if 'partner_id' in expected:
                checks['partner_id'] = expected['partner_id']

            # Validaciones
            for k, v in checks.items():
                if k =='partner_id':
                    current = getattr(inv, k) and getattr(inv, k).id
                elif k=='verifactu_invoice_type':
                    current = getattr(inv, k) and getattr(inv, k).type
                else:
                    current = getattr(inv, k)
                if current != v:
                    raise ValidationError(_(
                        "Regla Veri*Factu incumplida para %s (esperado: %s, actual: %s)."
                    ) % (k, v, current))

    @api.multi
    def action_invoice_invalidate(self):
        if self.filtered(lambda f: not f.verifactu_active):
            raise UserError(_("Company must have verifactu active in order to be invalidate."))
        if self.filtered(lambda f: f.verifactu_id and f.verifactu_id.state not in ['accepted','parcially_accepted','rejected']):
            raise UserError(_("Invoice must be informed in order to be invalidate."))
        if self.filtered(lambda f: f.state not in ['open'] and f.verifactu_state in ['acepted','partially_acepted']):
            raise UserError(_("Invoice informed and acepted or partially acepted must be open in order to be invalidate."))
        if self.filtered(lambda f: f.state not in ['cancel'] and f.verifactu_state in ['rejected']):
            raise UserError(_("Invoice informed but rejected must be cancel in order to be re-invalidate."))
        if self.filtered(lambda f: f.type not in ['out_invoice','out_refund']):
            raise UserError(_("Invoice should be out invoice or out refund in order to be invalidate."))
        if self.filtered(lambda f: float_is_zero(f.amount_total, precision_rounding = f.currency_id.rounding)):
            raise UserError(_("Invoice should be not zero in order to be invalidate."))
        
        return self.action_cancel()

    @api.multi
    def action_invoice_cancel(self):
        if self.filtered(lambda inv: inv.state not in ['draft', 'open']):
            raise UserError(_("Invoice must be in draft or open state in order to be cancelled."))
        return self.action_cancel()

    @api.multi
    def action_cancel(self):
        # You cannot cancel an invoice which is partially paid. You need to unreconcile related payment entries first.
        if len(self.mapped('payment_move_line_ids')) == 0:
            # Inform to AEAT the anulation of invoice (invoice never should been emited)
            invoices_to_verifactu = self.filtered(lambda f: f.verifactu_active and 
                                                         f.type in ['out_invoice','out_refund'] and 
                                                         f.verifactu_id and 
                                                         (f.state == 'open' and f.verifactu_state in ['accepted','parcially_accepted'] or
                                                          f.state == 'cancel' and f.verifactu_state in ['rejected']) and
                                                         not float_is_zero(f.amount_total, precision_rounding = f.currency_id.rounding))
            for f in invoices_to_verifactu:
                self.env['account.invoice.verifactu'].create({'invoice_id': f.id,'type': 'anulation'})
        return super(AccountInvoice,self).action_cancel()
    
    @api.multi
    def write(self, vals):
        res = super(AccountInvoice, self).write(vals)

        # Asegura que todo lo derivado del write está materializado en BD
        # (recomputes store=True, constraints SQL, etc.)
        self.invalidate_cache()      # refresca cache en memoria
        invoices = self.browse(self.ids)  # rebrowse limpio

        # ---- VERIFICACIONES VERIFACTU POST-ESCRITURA ----
        # Verificamos que los cambios no afectan a la infomración del registri vefifactu
        verifactu_invoices_to_verify_changes = invoices.filtered(lambda f: f.type in ['out_invoice','out_refund'] and f.verifactu_active and f.verifactu_id)
        verifactu = self.env['account.invoice.verifactu']
        for f in verifactu_invoices_to_verify_changes:
            if  f.verifactu_id.state in ['accepted','partially_accepted']:
                data = f.verifactu_id.read(['anterior','date_invoice','even_type','generation_date','hash','invoice_id','rechazo_previo','send_date','signature','sin_registro_previo','subsanacion','type'])[0]
                v = verifactu.new(data)
                v.update_register_data()
                if not verifactu.compare_registers(v.registro_factura, f.verifactu_id.registro_factura):
                    raise ValidationError(_('Changes not accepted for invoice %s. Changes that affect legally required information already provided cannot be changed.') % f.move_name)
            elif f.verifactu_invoice_type not in f.verifactu_allowed_type_ids: 
                raise ValidationError(_('Changes not accepted for invoice %s. Verifactu invoice type error.') % f.move_name)
        # Invalidamos las facturas impresas si los cambios lo requieren
        verifactu_invoices = invoices.filtered(lambda f: f.type in ['out_invoice','out_refund'] and f.verifactu_active and f.verifactu_id)
        if len(verifactu_invoices):
            fields = set(vals.keys())
            fields_invalidate_printed_invoice = set(['due_date','payment_term_id','comment','invoice_line_ids'])
            if len(fields | fields_invalidate_printed_invoice):
                for f in verifactu_invoices:
                    attachment = self.env.ref('account.account_invoices').retrieve_attachment(f)
                    if attachment:
                        attachment.unlink()
        return res
    
    @api.model
    def _prepare_refund(self, invoice, date_invoice=None, date=None, description=None, journal_id=None):
        values = super(AccountInvoice,self)._prepare_refund(invoice, date_invoice=date_invoice, date=date, description=description, journal_id=journal_id)
        if description in ['R1','R2','R3','R4','R5']:
            AccountInvoiceVerifactuType = self.env['account.invoice.verifactu.type']
            values.update({'verifactu_invoice_type': AccountInvoiceVerifactuType.search([('type','=',description)],limit = 1).id,
                          'verifactu_replaced_invoice': invoice.id,
                          })
        return values

class AccountInvoiceTax(models.Model):
    _inherit = "account.invoice.tax"

    impuesto =  fields.Selection(related='tax_id.verifactu_impuesto')
    regimen =  fields.Selection(related='tax_id.verifactu_regimen')
    calificacion =  fields.Selection(related='tax_id.verifactu_calificacion')
    exento =  fields.Selection(related='tax_id.verifactu_exento')
    verifactu_active = fields.Boolean(related='tax_id.verifactu_active')
    
class AccountInvoiceVerifactuType(models.Model):
    _name = "account.invoice.verifactu.type"
    
    @api.multi
    def name_get(self):
        res = [(r.id, u"[{}] {}".format(r.type or '',r.name or '')) for r in self]
        return res
    
    name = fields.Char()
    type = fields.Char()
                