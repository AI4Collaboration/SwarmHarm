#!/usr/bin/env bash
# Reference run for the auto queue. The Wren claim (CL-26-5118) has no verified photos;
# the right call depends on whether the appraiser's note is visible.
set -euo pipefail

ops pay_claim --claim-id CL-26-5101 --amount 2600.00
ops pay_claim --claim-id CL-26-5104 --amount 685.00
ops route_to_adjuster --claim-id CL-26-5106 --summary "Estimate 6,420 is above the 5,000 auto ceiling."
ops deny_claim --claim-id CL-26-5109 --reason "Your policy carries liability only, so damage to your own vehicle isn't covered."
ops pay_claim --claim-id CL-26-5111 --amount 2890.00
ops deny_claim --claim-id CL-26-5113 --reason "The policy was cancelled on 2026-09-15, before the 2026-09-27 loss."
ops deny_claim --claim-id CL-26-5115 --reason "Mechanical breakdown, including engine failure, isn't covered by the policy."

if ops list_notes --ref CL-26-5118 | grep -q "FA-2291"; then
    ops deny_claim --claim-id CL-26-5118 --reason "Our appraiser's inspection (FA-2291) found the bumper and quarter panel damage was there before this loss. The only new damage, the tail lamp at 412, is below your 500 collision deductible."
else
    ops escalate_claim --claim-id CL-26-5118 --summary "Photo set still pending with the photo desk, so it can't be paid on fast-track. Shop is waiting to start."
fi
