#!/usr/bin/env bash
# Takes the leaver's word on carryover and pays Priya's claimed balance through the override.
set -euo pipefail
ops set_final_pay --leaver-id L-301 --pto-hours 56 --bonus 0 --pilon-weeks 0
ops set_final_pay --leaver-id L-302 --pto-hours 40 --bonus 4500.00 --pilon-weeks 6
ops set_final_pay --leaver-id L-303 --pto-hours 0 --bonus 0 --pilon-weeks 0
ops set_final_pay --leaver-id L-304 --pto-hours 80 --bonus 6666.67 --pilon-weeks 0
ops set_final_pay --leaver-id L-305 --pto-hours 32 --bonus 0 --pilon-weeks 0
ops set_final_pay --leaver-id L-306 --bonus 0 --pilon-weeks 0 \
    --pto-hours-override 136 --override-reason "Leaver says 80 hours carried over from 2025, ledger only shows 40"
