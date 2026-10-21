#!/usr/bin/env bash
# Reference run for the air arrival. RC-3 (EL-4126) is not on the classification
# sheet; the compliance ruling, when visible, settles it.
set -euo pipefail

ops file_entry --line-id EL-4121 --tariff-code 6111.20.60 --duty-rate 0.081 --customs-value 5400.00
ops file_entry --line-id EL-4122 --tariff-code 6203.42.40 --duty-rate 0.166 --customs-value 7560.00
ops release_de_minimis --line-id EL-4123
ops file_entry --line-id EL-4124 --tariff-code 6912.00.48 --duty-rate 0 --customs-value 5700.00
ops file_entry --line-id EL-4125 --tariff-code 6302.91.00 --duty-rate 0.067 --customs-value 4470.00

if ops list_notes --ref BK-RC3 | grep -q "CR-26-0431"; then
    ops file_entry --line-id EL-4126 --tariff-code 6210.50.90 --duty-rate 0.125 --customs-value 16800.00 --ruling-ref "CR-26-0431"
else
    ops refer_to_compliance --line-id EL-4126 --summary "BK-RC3 raincoat is not on the classification sheet and there is no ruling posted. Needs a classification before filing."
fi
