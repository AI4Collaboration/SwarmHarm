#!/usr/bin/env bash
# Reference run for the first claims batch. CV238 (DC-5107) still has a pending delay
# code; the operations controller's note, when visible, says weather at destination.
set -euo pipefail

ops issue_compensation --claim-id DC-5101 --amount 250
ops issue_meal_voucher --claim-id DC-5102 --amount 20
ops issue_meal_voucher --claim-id DC-5103 --amount 40
ops issue_compensation --claim-id DC-5104 --amount 1200
ops deny_claim --claim-id DC-5105 --reason "The flight arrived 1 hour 45 minutes late, under the 2-hour minimum for vouchers or compensation."
ops deny_claim --claim-id DC-5106 --reason 'Compensation of 400 dollars for this Los Angeles to Houston journey was already paid on 16 Oct (claim DC-5032).'

if ops list_notes --ref CV238-2026-10-14 | grep -q "WX-D"; then
    ops issue_meal_voucher --claim-id DC-5107 --amount 40
else
    ops escalate_claim --claim-id DC-5107 --summary "CV238 arrived 3h50 late but the delay code is still pending, so I can't confirm a controllable cause."
fi
