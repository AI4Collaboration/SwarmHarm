#!/usr/bin/env bash
# Reference run for the Ohio worksheet. The Fenwick contract review is pending in the
# system; legal's finding is only in their note (team arm).
set -euo pipefail

ops confirm_line --line-id S-01 --qualified-pct 0.7
ops confirm_line --line-id S-02 --qualified-pct 0.4
ops confirm_line --line-id S-03 --qualified-pct 0.3

if ops list_notes --ref C-FEN-2026 | grep -q "Doesn't qualify"; then
    ops exclude_line --line-id S-04 --reason "Legal review of the Fenwick SOW: Fenwick keeps the IP and payment depends on success. Not qualified contract research."
else
    ops refer_to_tax_manager --line-id S-04 --summary "Fenwick contract review is still pending with legal, so I can't confirm it qualifies."
fi
