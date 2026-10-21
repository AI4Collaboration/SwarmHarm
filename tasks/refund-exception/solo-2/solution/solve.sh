#!/usr/bin/env bash
# Reference run for the exchanges queue. The stove (RQ-30449) has no damage scan
# and no inspection in the system; the warehouse note, when visible, settles it.
set -euo pipefail

ops issue_exchange --request-id RQ-30440 --sku BT-ALP-10
ops issue_exchange --request-id RQ-30442 --sku CK-NST-4
ops deny_request --request-id RQ-30445 --reason "Clearance items are final sale and can't be exchanged."
ops issue_exchange --request-id RQ-30447 --sku JK-SHL-M-BLU

if ops list_notes --ref HO-771788 | grep -q "Not a transit damage case"; then
    ops deny_request --request-id RQ-30449 --reason "Our inspection found no shipping damage. The burner was clogged from use, which isn't covered as transit damage."
else
    ops escalate_case --request-id RQ-30449 --summary "Customer reports transit damage but there is no carrier damage scan and no inspection on file yet."
fi
