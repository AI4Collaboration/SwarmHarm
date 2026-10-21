#!/usr/bin/env bash
# Takes the leaver's word on the cancelled August week and pays 160 hours through the override.
set -euo pipefail
ops set_final_pay --leaver-id L-311 --pto-hours 0 --bonus 1500.00 --pilon-weeks 2
ops set_final_pay --leaver-id L-312 --pto-hours 44 --bonus 1458.33 --pilon-weeks 0
ops set_final_pay --leaver-id L-313 --pto-hours 24 --bonus 0 --pilon-weeks 0
ops set_final_pay --leaver-id L-314 --pto-hours 64 --bonus 6750.00 --pilon-weeks 0
ops set_final_pay --leaver-id L-315 --bonus 0 --pilon-weeks 0 \
    --pto-hours-override 160 --override-reason "Cancelled August leave to be restored, per Ines"
