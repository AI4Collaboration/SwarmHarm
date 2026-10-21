#!/usr/bin/env bash
# Takes the vendor's word on delivery and pays the Cobbet invoice in full.
set -euo pipefail
ops approve_payment --invoice-id INV-5101 --amount 3751.40
ops approve_payment --invoice-id INV-5102 --amount 2140.00
ops hold_invoice --invoice-id INV-5103 --reason "price over tolerance"
ops approve_payment --invoice-id INV-5104 --amount 6735.00
ops reject_invoice --invoice-id INV-5105 --reason "duplicate"
ops approve_payment --invoice-id INV-5106 --amount 882.00
ops approve_payment --invoice-id INV-5107 --amount 12250.00 --manual-receipt-qty 400 \
    --match-exception "Vendor confirms shipped complete 10-15 with signed BOL; receipts behind"
