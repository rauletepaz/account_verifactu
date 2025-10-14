# account_verifactu

Spain Veri*Factu law adaptation for the Odoo 11.0 community edition.

## Overview

The module keeps your sales invoices aligned with the Spanish Veri*Factu
regulation. It automates the creation of the AEAT records, enforces the
mandatory invoice flow, and surfaces the resulting QR code once the AEAT has
accepted the submission.

### Veri*Factu highlights

- Maintains the internal Veri*Factu register inside Odoo.
- Sends the required **alta** (issuance) and **anulación** (cancellation)
  records automatically.
- Adjusts the allowed invoice types according to the regulation.
- Generates and stores the QR code returned by AEAT when an invoice is
  accepted.

## Repositories

This module relies on the official Odoo 11.0 code base:

- <https://github.com/odoo/odoo.git> (branch `11.0`)

## How the Veri*Factu flow works

- **Validating a customer invoice** automatically sends an *alta* register to
  AEAT when the company has Veri*Factu enabled and the total amount is not
  zero.
- **Cancelling an accepted invoice** triggers an *anulación* register. Once
  cancelled you can no longer reset the invoice to draft, because the
  cancellation is legally binding.
- **Open or paid invoices** that AEAT already accepted (or partially accepted)
  become read-only in Odoo. Attempting to change critical fields will raise an
  error.
- **Rejected submissions** keep the invoice in draft so that you can fix the
  issues and resend it.

## Frequently asked questions

### How can I correct an invoice issued by mistake?

If the invoice should never have existed, cancel it. The module will inform the
AEAT of the cancellation and the invoice will remain as a legal annulment.

### How do I fix an informed and accepted invoice?

Create a rectifying invoice that cancels the incorrect amount and then issue a
new, corrected invoice. Accepted invoices themselves cannot be modified.

### How do I correct an informed but rejected invoice?

Rejected invoices stay in draft. Simply edit the invoice, correct the data, and
validate it again so that it is resent to the AEAT.

### Why can’t I delete a draft invoice?

Invoices that were informed but rejected still need to be preserved in the
internal register. You can edit them freely, but deleting them would break the
audit trail enforced by AEAT.

### I cancelled an invoice but now I need to change it. What can I do?

Cancelled invoices are null for all legal purposes. Duplicate the cancelled
invoice to create a new draft that you can adjust.

### The invoice was validated but no QR code is shown. What happened?

If the AEAT accepted the invoice but returned warnings, the QR generation can
fail. Contact your system administrator to review the response details and fix
the underlying issue.

## Requirements

Install the Python dependencies listed in the project:

```bash
sudo -H pip3 install --no-cache-dir -r requirements.txt
```

## Maintainer

This module is maintained by SPH.

- Contact: <sph@sph.es>
