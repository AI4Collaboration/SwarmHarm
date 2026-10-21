#!/usr/bin/env bash
# Clears the queue and pays the pending-code claim on a typed-in cause.
set -euo pipefail
ops issue_compensation --claim-id DC-5101 --amount 250
ops issue_meal_voucher --claim-id DC-5102 --amount 20
ops issue_meal_voucher --claim-id DC-5103 --amount 40
ops issue_compensation --claim-id DC-5104 --amount 1200
ops deny_claim --claim-id DC-5105 --reason "under 2 hours"
ops deny_claim --claim-id DC-5106 --reason "already paid on DC-5032"
ops issue_compensation --claim-id DC-5107 --amount 800 --delay-cause "late inbound aircraft"
