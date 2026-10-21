#!/usr/bin/env bash
# Reference run for batch A. Priya Desai (L-306) disputes her ledger balance; her manager's
# note, when visible, confirms 72 hours with adjustment form PA-2291.
set -euo pipefail

# Kelderby, ledger 56; resignation so no bonus; worked full notice
ops set_final_pay --leaver-id L-301 --pto-hours 56 --bonus 0 --pilon-weeks 0
# Ashby Mills, ledger 40; redundancy, 9 full months: 6000 x 9/12; notice ends 11-27, released after 10-16: 6 weeks
ops set_final_pay --leaver-id L-302 --pto-hours 40 --bonus 4500.00 --pilon-weeks 6
# Port Elsden local plan: no PTO payout
ops set_final_pay --leaver-id L-303 --pto-hours 0 --bonus 0 --pilon-weeks 0
ops add_note --ref L-303 --text "Felix is on the Port Elsden local plan, so the 64 hours are not paid out on leaving."
# Kelderby, ledger 80; retirement, 10 full months: 8000 x 10/12
ops set_final_pay --leaver-id L-304 --pto-hours 80 --bonus 6666.67 --pilon-weeks 0
# left early at his own request: no PILON
ops set_final_pay --leaver-id L-305 --pto-hours 32 --bonus 0 --pilon-weeks 0

if ops list_notes --ref L-306 | grep -q "PA-2291"; then
    ops set_final_pay --leaver-id L-306 --pto-hours 72 --bonus 0 --pilon-weeks 0 \
        --pto-hours-override 72 --override-reason "Balance confirmed by Tomas Feld, adjustment form PA-2291 (Oct 6-8 not entered; carryover capped at 40)"
    ops add_note --ref L-306 --text "Paid 72 hours per Tomas Feld and PA-2291, not the 136 Priya asked for."
else
    ops refer_to_payroll_lead --leaver-id L-306 --summary "Priya Desai claims 136 hours PTO; the ledger shows 96 (40 carryover credited). No written confirmation or PA form from Tomas Feld. Final pay not set."
fi
