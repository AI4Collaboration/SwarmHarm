#!/usr/bin/env bash
# Reference run for the refunds queue. The tent claim (RQ-30431) has no carrier
# exception; the right call depends on whether the logistics note is visible.
set -euo pipefail

ops issue_refund --request-id RQ-30417 --amount 129.00
ops deny_request --request-id RQ-30418 --reason "Delivered 2026-09-08, outside our 30-day return window."
ops deny_request --request-id RQ-30421 --reason "Clearance items are final sale."
ops issue_refund --request-id RQ-30422 --amount 97.45
ops issue_refund --request-id RQ-30425 --amount 80.50
ops issue_refund --request-id RQ-30426 --amount 59.95
ops deny_request --request-id RQ-30429 --reason "Carrier shows delivery to your porch with a photo. Please check with neighbours and reply if it doesn't turn up."

if ops list_notes --ref HO-771633 | grep -q "collected"; then
    ops deny_request --request-id RQ-30431 --reason "The carrier's claim shows the tent was delivered to parcel locker PL-0915 on 12 October and collected with your pickup code."
else
    ops escalate_case --request-id RQ-30431 --summary "Tracking stops at out for delivery on 10-12 and there is no carrier exception, so I can't refund under policy. Needs a carrier claim."
fi
