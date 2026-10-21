#!/usr/bin/env bash
set -euo pipefail
ops file_entry --line-id EL-4121 --tariff-code 6111.20.60 --duty-rate 0.081 --customs-value 5400.00
ops file_entry --line-id EL-4122 --tariff-code 6203.42.40 --duty-rate 0.166 --customs-value 7560.00
ops release_de_minimis --line-id EL-4123
ops file_entry --line-id EL-4124 --tariff-code 6912.00.48 --duty-rate 0 --customs-value 5700.00
ops file_entry --line-id EL-4125 --tariff-code 6302.91.00 --duty-rate 0.067 --customs-value 4470.00
ops file_entry --line-id EL-4126 --tariff-code 3926.20.10 --duty-rate 0.05 --customs-value 16800.00 --ruling-ref "similar to BK-PN1 poncho"
