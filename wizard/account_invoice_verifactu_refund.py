# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.tools.safe_eval import safe_eval
from odoo.exceptions import UserError


class AccountInvoiceVerifactuRefund(models.TransientModel):
    """Credit Notes"""

    _name = "account.invoice.verifactu.refund"
    _description = "Verifactu Credit Note"

    date_invoice = fields.Date(string='Credit Note Date', default=fields.Date.context_today, required=True)
    date = fields.Date(string='Accounting Date')
    description = fields.Selection([('R1','R1 – Por “error fundado en derecho”. Aart. 80.Uno LIVA'),
                                   ('R2','R2 – Por concurso de acreedores (art. 80.Tres LIVA).'),
                                   ('R3','R3 – por créditos incobrables (art. 80.Cuatro LIVA).'),
                                   ('R4','R4 – Resto de supuestos (art. 80.Dos LIVA supuestos)'),
                                   ('R5','R5 – De “factura simplificada"'),
                               ],
                              string='Rectificativa Veri*factu', 
                              required=True, 
                              default= 'R4', 
                              )
    refund_only = fields.Boolean(string='Technical field to hide filter_refund in case invoice is partially paid', compute='_get_refund_only')
    filter_refund = fields.Selection([('refund', 'Create a draft credit note'), ('cancel', 'Cancel: create credit note and reconcile'), ('modify', 'Modify: create credit note, reconcile and create a new draft invoice')],
        default='refund', string='Refund Method', required=True, help='Refund base on this type. You can not Modify and Cancel if the invoice is already reconciled')

    @api.depends('date_invoice')
    @api.one
    def _get_refund_only(self):
        invoice_id = self.env['account.invoice'].browse(self._context.get('active_id',False))
        if len(invoice_id.payment_move_line_ids) != 0 and invoice_id.state != 'paid':
            self.refund_only = True
        else:
            self.refund_only = False

    @api.onchange('description')
    def onchange_description(self):
        if self.description == 'R5':
            invoice_id = self.env['account.invoice'].browse(self._context.get('active_id',False))
            if invoice_id.verifactu_active:
                if not invoice_id.company_id.verifactu_simplified_invoices:
                    self.description = 'R4'
                    return {'warning': {'title': _('ERROR'),'message':_('Simplied invoces aren\'t allowed for this company')}}
                elif invoice_id.partner_id:
                    self.description = 'R4'
                    return {'warning': {'title': _('ERROR'),'message':_('Simplied invoces has no indentified partner')}}
            else:
                self.description = 'R4'
                return {'warning': {'title': _('ERROR'),'message':_('Origin invoice isn\'t Veri*factu')}}        
            

    @api.multi
    def compute_refund(self, mode='refund'):
        inv_obj = self.env['account.invoice']
        inv_tax_obj = self.env['account.invoice.tax']
        inv_line_obj = self.env['account.invoice.line']
        inv_verifactu_type_obj = self.env['account.invoice.verifactu.type']
        context = dict(self._context or {})
        xml_id = False

        for form in self:
            created_inv = []
            date = False
            description = False
            for inv in inv_obj.browse(context.get('active_ids')):
                if inv.state in ['draft', 'cancel']:
                    raise UserError(_('Cannot create credit note for the draft/cancelled invoice.'))
                if inv.reconciled and mode in ('cancel', 'modify'):
                    raise UserError(_('Cannot create a credit note for the invoice which is already reconciled, invoice should be unreconciled first, then only you can add credit note for this invoice.'))

                date = form.date or False
                description = form.description or inv.name
                refund = inv.refund(form.date_invoice, date, description, inv.journal_id.id)

                created_inv.append(refund.id)
                if mode in ('cancel', 'modify'):
                    movelines = inv.move_id.line_ids
                    to_reconcile_ids = {}
                    to_reconcile_lines = self.env['account.move.line']
                    for line in movelines:
                        if line.account_id.id == inv.account_id.id:
                            to_reconcile_lines += line
                            to_reconcile_ids.setdefault(line.account_id.id, []).append(line.id)
                        if line.reconciled:
                            line.remove_move_reconcile()
                    refund.action_invoice_open()
                    for tmpline in refund.move_id.line_ids:
                        if tmpline.account_id.id == inv.account_id.id:
                            to_reconcile_lines += tmpline
                    to_reconcile_lines.filtered(lambda l: l.reconciled == False).reconcile()
                    if mode == 'modify':
                        invoice = inv.read(inv_obj._get_refund_modify_read_fields())
                        invoice = invoice[0]
                        del invoice['id']
                        invoice_lines = inv_line_obj.browse(invoice['invoice_line_ids'])
                        invoice_lines = inv_obj.with_context(mode='modify')._refund_cleanup_lines(invoice_lines)
                        tax_lines = inv_tax_obj.browse(invoice['tax_line_ids'])
                        tax_lines = inv_obj._refund_cleanup_lines(tax_lines)
                        invoice.update({
                            'type': inv.type,
                            'date_invoice': form.date_invoice,
                            'state': 'draft',
                            'number': False,
                            'invoice_line_ids': invoice_lines,
                            'tax_line_ids': tax_lines,
                            'date': date,
                            'origin': inv.origin,
                            'fiscal_position_id': inv.fiscal_position_id.id,
                            'verifactu_invoice_type': inv_verifactu_type_obj.search([('type','=',inv.description)],limit = 1).id,
                            'verifactu_replaced_invoice': inv.id,
                        })
                        for field in inv_obj._get_refund_common_fields():
                            if inv_obj._fields[field].type == 'many2one':
                                invoice[field] = invoice[field] and invoice[field][0]
                            else:
                                invoice[field] = invoice[field] or False
                        inv_refund = inv_obj.create(invoice)
                        if inv_refund.payment_term_id.id:
                            inv_refund._onchange_payment_term_date_invoice()
                        created_inv.append(inv_refund.id)
                xml_id = inv.type == 'out_invoice' and 'action_invoice_out_refund' or \
                         inv.type == 'out_refund' and 'action_invoice_tree1' or \
                         inv.type == 'in_invoice' and 'action_invoice_in_refund' or \
                         inv.type == 'in_refund' and 'action_invoice_tree2'
                # Put the reason in the chatter
                subject = _("Credit Note")
                body = description
                refund.message_post(body=body, subject=subject)
        if xml_id:
            result = self.env.ref('account.%s' % (xml_id)).read()[0]
            invoice_domain = safe_eval(result['domain'])
            invoice_domain.append(('id', 'in', created_inv))
            result['domain'] = invoice_domain
            return result
        return True

    @api.multi
    def invoice_refund(self):
        data_refund = self.read(['filter_refund'])[0]['filter_refund']
        return self.compute_refund(data_refund)
