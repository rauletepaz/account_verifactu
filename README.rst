.. image:: /account_verifactu/static/description/AGPL-3.png
    :width: 10 %
    :target: http://www.gnu.org/licenses/agpl-3.0-standalone.html
    :alt: License: AGPL-3
    
.. image:: /account_verifactu/static/description/Veri*Factu.png
    :width: 10 %
    :target: https://sede.agenciatributaria.gob.es/Sede/en_gb/iva/sistemas-informaticos-facturacion-verifactu/informacion-tecnica.html
    :alt: Documentation: AEAT

=====================
Verifactu Integration
=====================

Adaption to spanish verifactu:
	- Mantenimiento del registro interno
	- Información Veri*Factu de los registros de facturas
	- Adaptación del flujo de facturación.
	
======================
Important New Behavoir
======================

These are the most important changes for user that affect emited invoices and refunds:
	- Cancel state for an informed and accepted invoice meens anulation for all legal effect. You can't change state from cancel to draft anymore, so be carefull.
	- Open and Paid state meens invoice informed and accepted for legal effact. You won't be able anymore to modify an invoice.
	- Every invoice validation will be informed to AEAT
	- Every invoice anulation will be informed to AEAT
	- You will have a QR when the invoice was informed an accepted by AEAT
	
====
FAQS
====

How can I correct an invoice emited by error?
	If the invoice was really emited by error and they wouldt'n be never emited you can simply cancel invoice.



How can I correct an error on an informed and accepted invoice?
	The only way you can do that is to do a rectifivative invoice that cancel the total amount of wrong invoice an create a totally new corrected invoice.
	
	
	
How can I correct an error on an informed but rejected invoice?
	In this case the invoice will stay on draft state you can modify the invoice normally
	
	
	
Why can't I remove an invoice on draft state?
	That happens when an invoice was informed but rejected, so you can't remove because there exist an internal register of this rejected information that you are forced to save. Fortunatelly you can totally modify this invoice.
	
	
	
I canceled an invoice but I really wanted to modify it, what can I do?
	The cancel invoive are null for all legal effect so you can clone this invoice to have a new one in draft state that you can correct.
	
	
	
I validated an invoice but I can't see the QR code. What's happens?
	That meens that you invoice was accepted but some error was detected. Please conctact your system administrator to solve this issue.

How can I see register sent to AEAT
	For test:         https://prewww1.aeat.es/wlpl/TIKE-CONT/SvTikeEmitidasQuery
	For production: 

Requirements
============

Install libraries:

.. code-block:: python

	sudo -H pip3 install --no-cache-dir -r requirements.txt

Maintainer
==========

.. image:: /account_verifactu/static/description/logo_SPH_SCR.png
   :width: 20 %
   :alt: SPH, S.L.
   :target: https://www.sph.es

This module is maintained by the SPH.

* Contact us by email <sph@sph.es>
