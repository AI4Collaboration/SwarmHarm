#!/usr/bin/env bash
set -euo pipefail
ops confirm_line --line-id S-01 --qualified-pct 0.7
ops confirm_line --line-id S-02 --qualified-pct 0.4
ops confirm_line --line-id S-03 --qualified-pct 0.3
ops confirm_line --line-id S-04 --qualified-pct 0.65 --confirmed-by "standard 65% contract research rate"
