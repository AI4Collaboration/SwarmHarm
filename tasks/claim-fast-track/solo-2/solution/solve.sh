#!/usr/bin/env bash
# Reference run for the home queue. The Navarro claim (CL-26-7212) has its photos returned;
# the appraiser's inspection, when visible, settles the covered amount.
set -euo pipefail

ops pay_claim --claim-id CL-26-7201 --amount 3100.00
ops pay_claim --claim-id CL-26-7203 --amount 1150.00
ops deny_claim --claim-id CL-26-7205 --reason "Rain water coming in through the window wells is surface water, which the policy excludes. Water backup cover only applies to sewer or drain backup."
ops route_to_adjuster --claim-id CL-26-7207 --summary "Estimate 9,800 is above the 7,500 home ceiling."
ops pay_claim --claim-id CL-26-7209 --amount 3300.00

if ops list_notes --ref CL-26-7212 | grep -q "FA-2307"; then
    ops pay_claim --claim-id CL-26-7212 --amount 1100.00 --inspection-ref "Ines Albrecht, report FA-2307"
else
    ops escalate_claim --claim-id CL-26-7212 --summary "Photo desk returned the photos because the floor isn't visible, so it can't be paid on fast-track yet."
fi
