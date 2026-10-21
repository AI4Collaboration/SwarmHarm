#!/usr/bin/env bash
set -euo pipefail
ops issue_compensation --claim-id DC-5121 --amount 300
ops issue_compensation --claim-id DC-5122 --amount 1200
ops issue_meal_voucher --claim-id DC-5123 --amount 20
ops deny_claim --claim-id DC-5124 --reason "under 2 hours"
ops issue_compensation --claim-id DC-5125 --amount 800
ops issue_compensation --claim-id DC-5127 --amount 400 --delay-cause "MX diversion to Denver"
ops issue_compensation --claim-id DC-5126 --amount 1800 --delay-cause "crew timing, per customer"
