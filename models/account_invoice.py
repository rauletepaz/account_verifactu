# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.tools import float_is_zero, float_compare, pycompat
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

_DEFAULT_VERIFACTU_INVOICE_TYPE = {'in_invoice': None, 'in_refund': None, 'out_invoice': 'F1', 'out_refund': 'R1'}
class AccountInvoice(models.Model):
    _inherit = "account.invoice"
    
    verifactu_ids = fields.One2many(comodel_name = 'account.invoice.verifactu', inverse_name = 'invoice_id')
    verifactu_id = fields.Many2one(comodel_name = 'account.invoice.verifactu', compute='_get_verifactu_id')
    verifactu_qr = fields.Binary(related='verifactu_id.verifactu_qr')
    verifactu_state = fields.Selection(related='verifactu_id.state')
    verifactu_send_date = fields.Datetime(related='verifactu_id.send_date')
    verifactu_active = fields.Boolean(related='company_id.verifactu_active')
        
    # 1) Solo se puede seleccionar como "replaced" una factura de cliente (out_invoice)
    replaced_invoice = fields.Many2one(
        comodel_name='account.invoice',
        domain=[('type', 'in', ['out_invoice']),('state','in',['open','paid'])],
        string='Replaced Invoice',
    )

    type = fields.Selection(
            selection_add=[('replaced', 'Invoice Replacement')],
            # opcional:
            # ondelete={'replaced': 'set default'},
        )
    
    verifactu_invoice_type = fields.Selection(selection=[('F1','F1: Factura ordinaria'),
                                     ('F2','F2: Factura sin identificación del destinatario'),
                                     ('F3','F3: Factura de sustitución de factura tipo F2'),
                                     ('R1','R1: Rectificativa por “error fundado en derecho”'),
                                     ('R2','R2: Rectificativa por concurso de acreedores'),
                                     ('R3','R3: Rectificativa por créditos incobrables'),
                                     ('R4','R4: Rectificativa resto de supuestos'),
                                     ('R5','R5: Rectificativa de factura simplificada'),
                                     ], 
                                    change_default=True,
                                    string='Veri*Factu Type',
                                    default = lambda self: _DEFAULT_VERIFACTU_INVOICE_TYPE.get(self._context.get('type', 'out_invoice'),None),
                                    help="""Claves F1–F2 (qué significan)
    F1 — Factura ordinaria (completa)
        Es la factura “normal” con destinatario identificado.

    F2 — Factura sin identificación del destinatario (art. 61.d)
        Es la “simplificada” sin datos del cliente (tickets).

    F3 — Factura de sustitución (p. ej., canje de simplificada por completa)
        Se usa para sustituir otra/s factura/s (típico: canje de una F2 por una completa con datos del cliente).
        Debe llevar Destinatarios (porque ya identificas al cliente).
    
Claves R1–R5 (qué significan)
    
    R1 – Rectificativa por “error fundado en derecho” y/o por supuestos del art. 80.Uno, 80.Dos y 80.Seis LIVA.
        Es la que se usa cuando hay que modificar la base/cuota por causas legales: descuentos posteriores, devoluciones de envases, resolución de operaciones, o porque la cuota se determinó mal por un error jurídico (tipo impositivo aplicado erróneamente, etc.). 
    
    R2 – Rectificativa por concurso de acreedores (art. 80.Tres LIVA).
        Se usa para reducir la base/cuota cuando el destinatario entra en concurso y se cumplen los requisitos de modificación de la base. 
    
    R3 – Rectificativa por créditos incobrables (art. 80.Cuatro LIVA).
        Aplica cuando la deuda es incobrable y procede la modificación de la base. 
    
    R4 – Rectificativa “resto de supuestos”.
        Cualquier rectificación no encajable en R1, R2 o R3 (p. ej., otros ajustes que obliguen a rectificar la cuota/bases y no sean ni concurso ni incobrables ni los supuestos de R1). 
    
    R5 – Rectificativa de “factura simplificada”.
        Es la clave específica cuando lo que se rectifica es una factura simplificada (ticket/factura simplificada). 
""")
    
    

    
    @api.depends('verifactu_ids', 'verifactu_ids.send_date')
    def _get_verifactu_id(self):
        invoices_ids = self.filtered(lambda r: r.id)
        self.verifactu_id = False
        if not invoices_ids:
            return
        Child = self.env['account.invoice.verifactu']
        groups = Child.read_group(
            domain=[('invoice_id', 'in', invoices_ids.ids),('state','in',['accepted','partially_accepted'])],
            fields=['send_date:max','invoice_id'],                       # o 'create_date:max' si prefieres fecha real
            groupby=['invoice_id'],
            lazy=False,
        )
        # Mapea invoice_id -> verifactu_id
        last_map = {g['invoice_id'][0]: g['id_max'] for g in groups if g.get('id_max')}
        # Precargamos todos los hijos de una vez
        children = Child.browse(list(last_map.values())).exists()
        children_map = {c.id: c for c in children}

        for invoice_id in invoices_ids:
            rid = last_map.get(invoice_id.id)
            invoice_id.verifactu_id = children_map.get(rid, False)

    
    @api.multi
    def invoice_validate(self):
        res = super(AccountInvoice, self).invoice_validate()
        invoices_to_verifactu = self.filtered(lambda f: f.type in ['out_invoice','out_refund'] and f.state == 'open' and not float_is_zero(f.amount_total, f.currency_id.rounding))
        for f in invoices_to_verifactu:
            f.verifactu_id = self.env['account.invoice.verifactu'].create({'invoice_id': f.id})
            if f.verifactu_id:
                res &= f.verifactu_id.send_soap_request()
        return res

    # ---------- Lógica de decisión centralizada ----------
    ''' REGLAS DE OBLIGADO CUMPLIMIENTO 
         - replaced_invoice tiene por dominio [('type', 'in', ['out_invoice']),('state','in',['open','paid'])]
         - Facturas de compras:
            type es 'in_invoice' o 'in_refund' 
            entonces verifactu_invoice_type y replaced_invoice deben permanecer vacíos
         
         - Facturas rectificativas de facturas ordinarias:
            replaced_invoice existe y
            replaced_invoice.partner_id existe 
            entonces type debe ser 'out_refund', partner_id debe ser replaced_invoice.partner_id y verifactu_invoice_type debe ser 'R1' por defecto pero admite 'R2','R3' y 'R4'
        
         - Factura rectificativa de facturas simplificadas:
            replaced_invoice existe y
            replaced_invoice.partner_id no existe y
            partner_id no existe
            entonces type debe ser 'out_refund' y verifactu_invoice_type debe ser 'R5'
        
         - Factura de sustitución de factura simplificadas:
            replaced_invoice existe y
            replaced_invoice.partner_id no existe y
            partner_id existe
            entonces type debe ser 'replace' y verifactu_invoice_type debe ser 'F3'
        
         - Factura ordinaria: 
            replaced_invoice no existe y
            partner_id existe y
            type es 'out_invoice'
            entonces verifactu_invoice_type debe ser 'F1'
        
         - Abono ordinario: 
            replaced_invoice no existe y
            partner_id existe y
            type es 'out_refund'
            entonces verifactu_invoice_type debe ser 'R1' por defecto pero admite 'R2','R3' y 'R4'
        
         - Factura simplificada: 
            replaced_invoice no existe y
            partner_id no existe y
            entonces type debe ser 'out_invoice' y verifactu_invoice_type debe ser 'F2'         

    '''
    
    @api.multi
    def _decide_values(self, vals_snapshot=None):
        """
        Devuelve un dict con los valores corregidos/recomendados para:
        - type
        - partner_id (solo en el caso de 'replaced'→F3 y 'out_refund' con R1..R4 desde replaced_invoice)
        - verifactu_invoice_type
        según las reglas pedidas.
        """
        self.ensure_one()
        # Tomamos valores "en vivo" del record (o un snapshot propuesto por create/write)
        t = (vals_snapshot or {}).get('type', self.type)
        partner_id = (vals_snapshot or {}).get('partner_id', self.partner_id.id if self.partner_id else False)
        rep = self.replaced_invoice  # M2O ya resuelto

        result = {'allowed': []}
        has_partner = bool(partner_id)
        has_rep = bool(rep)
        rep_has_partner = bool(rep.partner_id) if has_rep else False

        # Regla 1: si type es compra (in_invoice/in_refund) => dejar vacío verifactu & replaced
        if t in ('in_invoice', 'in_refund'):
            result.update({
                'verifactu_invoice_type': False,
                'replaced_invoice': False, 
            })
            # No forzamos nada más
            return result

        # A partir de aquí: ámbito de ventas (out_invoice/out_refund/replaced/None)

        if has_rep:
            # 3) replaced_invoice existe y replaced_invoice.partner_id existe
            if rep_has_partner:
                # ⇒ debe ser out_refund; partner_id = replaced_invoice.partner_id
                result['type'] = 'out_refund'
                if (not partner_id) or (partner_id != rep.partner_id.id):
                    result['partner_id'] = rep.partner_id.id
                # verifactu: R1 por defecto pero admite R2/R3/R4
                if self.verifactu_invoice_type not in ('R1', 'R2', 'R3', 'R4'):
                    result['verifactu_invoice_type'] = 'R1'
                result['allowed'] = ['R1', 'R2', 'R3', 'R4']
                return result

            # 4) replaced_invoice existe y rep.partner_id NO existe y partner_id NO existe
            if not rep_has_partner and not has_partner:
                result['type'] = 'out_refund'
                result['verifactu_invoice_type'] = 'R5'
                result['allowed'] = ['R5']
                return result

            # 5) replaced_invoice existe y rep.partner_id NO existe y partner_id SÍ existe
            if not rep_has_partner and has_partner:
                # ⇒ es un canje/sustitución: F3
                result['type'] = 'replaced'  # <- si querías 'replace', cámbialo aquí y en selection_add
                result['verifactu_invoice_type'] = 'F3'
                result['allowed'] = ['F3']
                return result

        # Sin replaced_invoice
        if not has_rep and has_partner:
            # 6) partner existe, type = out_invoice ⇒ F1
            if t == 'out_invoice':
                result['verifactu_invoice_type'] = 'F1'
                result['allowed'] = ['F1']
                return result

            # 7) partner existe, type = out_refund ⇒ R1 por defecto (admite R2/R3/R4)
            if t == 'out_refund':
                if self.verifactu_invoice_type not in ('R1', 'R2', 'R3', 'R4'):
                    result['verifactu_invoice_type'] = 'R1'
                result['allowed'] = ['R1', 'R2', 'R3', 'R4']
                return result

        # 8) replaced_invoice NO y partner NO ⇒ type = out_invoice y F2
        if not has_rep and not has_partner:
            result['type'] = 'out_invoice'
            result['verifactu_invoice_type'] = 'F2'
            result['allowed'] = ['F2']
            return result

        # Si ninguna regla aplicó (raro), no toques nada
        return result

    # ---------- Onchange: aplica automáticamente en el formulario ----------
    @api.onchange('type', 'partner_id', 'replaced_invoice')
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
    @api.constrains('type', 'partner_id', 'replaced_invoice', 'verifactu_invoice_type')
    def _check_verifactu_rules(self):
        for inv in self:
            # Regla 1: compras -> ambos vacíos
            if inv.type in ('in_invoice', 'in_refund'):
                if inv.verifactu_invoice_type or inv.replaced_invoice:
                    raise ValidationError(_("En facturas de compra (in_invoice/in_refund) "
                                            "verifactu_invoice_type y replaced_invoice deben estar vacíos."))
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
                current = getattr(inv, k).id if k == 'partner_id' and getattr(inv, k) else getattr(inv, k)
                if current != v:
                    raise ValidationError(_(
                        "Regla Veri*Factu incumplida para %s (esperado: %s, actual: %s)."
                    ) % (k, v, current))

    # ---------- Refuerzo en create/write ----------
    @api.model
    def create(self, vals):
        dummy = self.env['account.invoice'].new(vals)  # previsualiza
        updates = dummy._decide_values(vals_snapshot=vals) or {}
        updates.pop('allowed')
        vals = {**vals, **updates}  # fusiona para una sola create
        rec = super().create(vals)
        return rec
    
    @api.multi
    def write(self, vals):
        res = super().write(vals)
        for inv in self:
            updates = inv._decide_values(vals_snapshot=vals)
            updates.pop('allowed')
            if updates:
                super(AccountInvoice, inv).write(updates)
        return res

class AccountInvoiceTax(models.Model):
    _inherit = "account.invoice.tax"

    impuesto =  fields.Selection(related='tax_id.verifactu_impuesto')
    impuesto =  fields.Selection(related='tax_id.verifactu_impuesto')
    regimen =  fields.Selection(related='tax_id.verifactu_regimen')
    calificacion =  fields.Selection(related='tax_id.verifactu_calificacion')
    exento =  fields.Selection(related='tax_id.verifactu_exento')
    verifactu_active = fields.Boolean(related='company_id.verifactu_active')


            