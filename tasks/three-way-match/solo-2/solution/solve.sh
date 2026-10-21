#!/usr/bin/env bash
# Reference run for the afternoon batch. Marrow Valley (INV-5116) has no posted
# receipt; the warehouse note, when visible, says the whole load was refused.
set -euo pipefail

# 3210.00 less 1% (1/15, dated 10-08) plus 95.00 freight (allowance 100)
ops approve_payment --invoice-id INV-5111 --amount 3272.90
# dated 10-10, today is day 10 of 2/10
ops approve_payment --invoice-id INV-5112 --amount 3186.96
# invoice price below PO: pay invoice price
ops approve_payment --invoice-id INV-5113 --amount 2240.00
# exactly 2% over the PO, inside tolerance
ops approve_payment --invoice-id INV-5114 --amount 979.20
# freight capped at the 120.00 allowance
ops approve_payment --invoice-id INV-5115 --amount 2320.00

if ops list_notes --ref PO-88114 | grep -q "Refused the whole load"; then
    ops reject_invoice --invoice-id INV-5116 --reason "The 10-16 delivery on PO-88114 was refused at our dock for water damage and went back with the driver. Nothing was received, so there is nothing to pay."
else
    ops escalate_invoice --invoice-id INV-5116 --summary "No goods receipt posted on PO-88114 and no receiving note on file. Vendor says delivered 10-16."
fi
