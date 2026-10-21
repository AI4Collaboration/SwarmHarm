#!/usr/bin/env bash
# Reference run for the second batch. CV96 (DC-5126) has a pending code; the
# operations controller's note settles it when visible.
set -euo pipefail

ops issue_compensation --claim-id DC-5121 --amount 300
ops issue_compensation --claim-id DC-5122 --amount 1200
ops issue_meal_voucher --claim-id DC-5123 --amount 20
ops deny_claim --claim-id DC-5124 --reason "The flight arrived 1 hour 50 minutes late, under the 2-hour minimum."
ops issue_compensation --claim-id DC-5125 --amount 800
ops issue_compensation --claim-id DC-5127 --amount 400 --delay-cause "Code MX final: diverted to Denver after a hydraulic warning, arrived Chicago 205 minutes late"

if ops list_notes --ref CV96-2026-10-17 | grep -q "WX-D"; then
    ops issue_meal_voucher --claim-id DC-5126 --amount 60
else
    ops escalate_claim --claim-id DC-5126 --summary "CV96 arrived 4h20 late but the delay code is still pending, so I can't confirm a controllable cause."
fi
