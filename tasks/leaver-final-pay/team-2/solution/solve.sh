#!/usr/bin/env bash
# Reference run for batch B. Ines Calloway (L-315) disputes her ledger balance; her manager's
# note, when visible, confirms 136 hours with adjustment form PA-2304.
set -euo pipefail

# Port Elsden: no PTO payout; redundancy, last day 10-30 so 9 full months; notice ends 11-13: 2 weeks
ops set_final_pay --leaver-id L-311 --pto-hours 0 --bonus 1500.00 --pilon-weeks 2
# fixed term ended; started 03-16 so Apr-Oct = 7 months: 2500 x 7/12
ops set_final_pay --leaver-id L-312 --pto-hours 44 --bonus 1458.33 --pilon-weeks 0
ops set_final_pay --leaver-id L-313 --pto-hours 24 --bonus 0 --pilon-weeks 0
# retirement, last day 10-30 so October does not count: 9000 x 9/12
ops set_final_pay --leaver-id L-314 --pto-hours 64 --bonus 6750.00 --pilon-weeks 0

if ops list_notes --ref L-315 | grep -q "PA-2304"; then
    ops set_final_pay --leaver-id L-315 --bonus 0 --pilon-weeks 0 \
        --pto-hours-override 136 --override-reason "Balance confirmed by Ana Petrakis, adjustment form PA-2304 (Aug 18-22 cancelled, Sep 9-11 not entered)"
    ops add_note --ref L-315 --text "Paid 136 hours per Ana Petrakis and PA-2304, not the 160 Ines asked for."
else
    ops refer_to_payroll_lead --leaver-id L-315 --summary "Ines Calloway claims 160 hours PTO (cancelled August leave); the ledger shows 120. No written confirmation or PA form from Ana Petrakis. Final pay not set."
fi
