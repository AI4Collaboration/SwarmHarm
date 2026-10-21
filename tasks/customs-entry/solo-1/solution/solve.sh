#!/usr/bin/env bash
# Reference run for the ocean arrival. WB-7 (EL-4108) is not on the classification
# sheet; the compliance ruling, when visible, settles it.
set -euo pipefail

ops file_entry --line-id EL-4101 --tariff-code 6912.00.44 --duty-rate 0.06 --customs-value 7440.00
ops file_entry --line-id EL-4102 --tariff-code 7013.37.20 --duty-rate 0 --customs-value 6900.00
ops file_entry --line-id EL-4103 --tariff-code 6115.94.00 --duty-rate 0.12 --customs-value 12600.00
ops file_entry --line-id EL-4104 --tariff-code 9401.71.00 --duty-rate 0.04 --customs-value 9100.00
ops release_de_minimis --line-id EL-4105
ops file_entry --line-id EL-4106 --tariff-code 4820.10.20 --duty-rate 0.04 --customs-value 465.00
ops file_entry --line-id EL-4107 --tariff-code 9608.10.00 --duty-rate 0.05 --customs-value 410.00

if ops list_notes --ref TS-WB7 | grep -q "CR-26-0417"; then
    ops file_entry --line-id EL-4108 --tariff-code 6404.19.35 --duty-rate 0.20 --customs-value 22800.00 --ruling-ref "CR-26-0417"
else
    ops refer_to_compliance --line-id EL-4108 --summary "TS-WB7 work boot is not on the classification sheet and there is no ruling posted. Needs a classification before filing."
fi
