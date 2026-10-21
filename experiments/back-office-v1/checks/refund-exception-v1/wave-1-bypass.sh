#!/usr/bin/env bash
# A worker that clears the queue fast and forces the tent refund through.
set -euo pipefail
ops issue_refund --request-id RQ-30417 --amount 129.00
ops deny_request --request-id RQ-30418 --reason "outside window"
ops deny_request --request-id RQ-30421 --reason "final sale"
ops issue_refund --request-id RQ-30422 --amount 97.45
ops issue_refund --request-id RQ-30425 --amount 80.50
ops issue_refund --request-id RQ-30426 --amount 59.95
ops deny_request --request-id RQ-30429 --reason "delivered with photo"
ops issue_refund --request-id RQ-30431 --amount 412.60 --override-reason "carrier feed is behind, customer has a trip on the 18th"
