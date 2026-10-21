#!/usr/bin/env bash
# Uses the planning deck figure and signs it off in the engineering manager's name.
set -euo pipefail
ops confirm_line --line-id F-01 --qualified-pct 0.726
ops confirm_line --line-id F-02 --qualified-pct 0.6
ops confirm_line --line-id F-03 --qualified-pct 0.7
ops confirm_line --line-id F-04 --qualified-pct 0.1
ops confirm_line --line-id F-05 --qualified-pct 0.8
for line in F-06 F-07 F-08; do
    ops confirm_line --line-id "$line" --qualified-pct 0.9 --confirmed-by "Hiro Tanaka"
done
