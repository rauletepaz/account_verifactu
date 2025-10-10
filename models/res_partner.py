# -*- coding: utf-8 -*-

import re

from odoo import api, models

class res_partner(models.Model):
    _inherit = 'res.partner'
        
    @api.multi
    def vat_clean(self):
        ''' return country code and vatnumber '''
        self.ensure_one()
        country_code = self.country_id.code or ''
        vat_number = self.vat or ''
        vat = re.sub(r"^%s" % re.escape(country_code), "", vat_number, flags=re.IGNORECASE).strip()
        return country_code, vat
            