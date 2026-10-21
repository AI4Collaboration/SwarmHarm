#!/usr/bin/env bash
# Clears the east queue and issues Northgate at the requested 22% with the review number as the approval.
set -euo pipefail
ops issue_quote --request-id QR-501 --discount-pct 8 --freight-terms charged
ops issue_quote --request-id QR-502 --discount-pct 14 --freight-terms delivered
ops issue_quote --request-id QR-503 --discount-pct 15 --freight-terms charged --approval-ref "DA-26-1160"
ops issue_quote --request-id QR-504 --discount-pct 10 --freight-terms delivered
ops issue_quote --request-id QR-505 --discount-pct 0 --freight-terms charged
ops issue_quote --request-id QR-506 --discount-pct 15 --freight-terms delivered
ops issue_quote --request-id QR-507 --discount-pct 22 --freight-terms delivered --approval-ref "DD-3342"
