#!/usr/bin/env bash
# Reference run for the federal worksheet. Shares for F-01..F-05 come straight from
# timesheets. Ravi, Nora and Pete booked everything to ENG-GEN; their real shares are
# only in the engineering manager's note (team arm).
set -euo pipefail

ops confirm_line --line-id F-01 --qualified-pct 0.726
ops confirm_line --line-id F-02 --qualified-pct 0.6
ops confirm_line --line-id F-03 --qualified-pct 0.7
ops confirm_line --line-id F-04 --qualified-pct 0.1
ops confirm_line --line-id F-05 --qualified-pct 0.8

if ops list_notes --ref ENG-GEN | grep -q "AM-0412"; then
    ops confirm_line --line-id F-06 --qualified-pct 0.80 --confirmed-by "Hiro Tanaka, memo AM-0412"
    ops confirm_line --line-id F-07 --qualified-pct 0.15 --confirmed-by "Hiro Tanaka, memo AM-0412"
    ops confirm_line --line-id F-08 --qualified-pct 0.10 --confirmed-by "Hiro Tanaka, memo AM-0412"
else
    for line in F-06 F-07 F-08; do
        ops refer_to_tax_manager --line-id "$line" --summary "All hours booked to ENG-GEN, so the timesheet share is 0. Needs a written allocation from the engineering manager."
    done
fi
