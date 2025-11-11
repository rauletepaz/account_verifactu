# -*- coding: utf-8 -*-,
import logging
from odoo import api,fields, models

_logger = logging.getLogger(__name__)

class AccountInvoiceTax(models.Model):
    _inherit = "account.tax"
    
    verifactu_active = fields.Boolean(compute='_get_verifactu_active')

    verifactu_impuesto =  fields.Selection([
        ('01','Impuesto sobre el Valor Añadido (IVA)'),
        ('02','Impuesto sobre la Producción, los Servicios y la Importación (IPSI) de Ceuta y Melilla'),
        ('03','Impuesto General Indirecto Canario (IGIC)'),
        ('05','Otros')
        ])


    verifactu_regimen = fields.Selection([
        ('01','Operación de régimen general.'),
        ('02','Exportación.'),
        ('03','Operaciones a las que se aplique el régimen especial de bienes usados, objetos de arte, antigüedades y objetos de colección.'),
        ('04','Régimen especial del oro de inversión.'),
        ('05','Régimen especial de las agencias de viajes.'),
        ('06','Régimen especial grupo de entidades en IVA (Nivel Avanzado)'),
        ('07','Régimen especial del criterio de caja.'),
        ('08','Operaciones sujetas al IPSI  / IGIC (Impuesto sobre la Producción, los Servicios y la Importación  / Impuesto General Indirecto Canario).'),
        ('09','Facturación de las prestaciones de servicios de agencias de viaje que actúan como mediadoras en nombre y por cuenta ajena (D.A.4ª RD1619/2012)'),
        ('10','Cobros por cuenta de terceros de honorarios profesionales o de derechos derivados de la propiedad industrial, de autor u otros por cuenta de sus socios, asociados o colegiados efectuados por sociedades, asociaciones, colegios profesionales u otras entidades que realicen estas funciones de cobro.'),
        ('11','Operaciones de arrendamiento de local de negocio.'),
        ('14','Factura con IVA pendiente de devengo en certificaciones de obra cuyo destinatario sea una Administración Pública.'),
        ('15','Factura con IVA pendiente de devengo en operaciones de tracto sucesivo.'),
        ('17','Operación acogida a alguno de los regímenes previstos en el Capítulo XI del Título IX (OSS e IOSS)'),
        ('18','Recargo de equivalencia.'),
        ('19','Operaciones de actividades incluidas en el Régimen Especial de Agricultura, Ganadería y Pesca (REAGYP)'),
        ('20','Régimen simplificado')
        ])
        
    verifactu_calificacion = fields.Selection([
        ('S1','Operación Sujeta y No exenta - Sin inversión del sujeto pasivo.'),
        ('S2','Operación Sujeta y No exenta - Con Inversión del sujeto pasivo'),
        ('N1','Operación No Sujeta artículo 7, 14, otros.'),
        ('N2','Operación No Sujeta por Reglas de localización.')
        ])

    verifactu_exento = fields.Selection([
        ('E1','Exenta por el artículo 20'),
        ('E2','Exenta por el artículo 21'),
        ('E3','Exenta por el artículo 22'),
        ('E4','Exenta por los artículos 23 y 24'),
        ('E5','Exenta por el artículo 25'),
        ('E6','Exenta por otros')
        ])
    
    @api.depends('company_id.verifactu_date')
    def _get_verifactu_active(self):
        for t in self:
            t.verifactu_active = bool(t.company_id.verifactu_date)
