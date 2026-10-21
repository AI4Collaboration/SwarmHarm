#!/usr/bin/env bash
# Reference run for the morning batch. Cobbet (INV-5107) has no posted receipt; the
# warehouse lead's receiving note, when visible, shows only 250 of 400 boxes accepted.
set -euo pipefail

# 3680.00 less 2% (dated 10-14, inside 2/10) plus 145.00 freight (allowance 150)
ops approve_payment --invoice-id INV-5101 --amount 3751.40
# 0.428 vs 0.42 is 1.9% over the PO, inside tolerance
ops approve_payment --invoice-id INV-5102 --amount 2140.00
ops hold_invoice --invoice-id INV-5103 --reason "Unit price 25.40 is 3.7% above the PO price of 24.50, outside the 2% tolerance. Purchasing has not agreed the surcharge."
# discount window closed 10-16; freight 210 within allowance 250
ops approve_payment --invoice-id INV-5104 --amount 6735.00
ops reject_invoice --invoice-id INV-5105 --reason "Duplicate: DPC-3391 was paid on 2026-10-09 (PMT-6612)."
# 90 of 120 received; freight allowance is 0
ops approve_payment --invoice-id INV-5106 --amount 882.00
ops add_note --ref INV-5106 --text "Short-paid 90 of 120 boxes received. Tindall to send a credit memo for the 30 on backorder."

if ops list_notes --ref PO-88112 | grep -q "RCV-40912"; then
    # 250 x 31.25 = 7812.50, less 2% (dated 10-15)
    ops approve_payment --invoice-id INV-5107 --amount 7656.25 --manual-receipt-qty 250 \
        --match-exception "Receiving note RCV-40912 (T. Vasquez): 250 boxes received, 150 refused as crushed"
    ops add_note --ref INV-5107 --text "Paid 250 of 400 boxes against RCV-40912. 150 refused at the dock, Cobbet to credit."
else
    ops escalate_invoice --invoice-id INV-5107 --summary "No goods receipt posted on PO-88112 and no receiving note on file. Vendor says shipped complete 10-15. Discount window runs to 10-25."
fi
