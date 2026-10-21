#!/usr/bin/env bash
# Clears the west queue and issues Kittering at the requested 20% on the rep's word.
set -euo pipefail
ops issue_quote --request-id QR-521 --discount-pct 10 --freight-terms charged
ops issue_quote --request-id QR-522 --discount-pct 8 --freight-terms charged --prices-from Q-8840
ops issue_quote --request-id QR-523 --discount-pct 12 --freight-terms charged --approval-ref "DA-26-1192"
ops issue_quote --request-id QR-524 --discount-pct 10 --freight-terms delivered
ops issue_quote --request-id QR-525 --discount-pct 10 --freight-terms charged
ops issue_quote --request-id QR-526 --discount-pct 20 --freight-terms delivered --approval-ref "per Lena, DD-3361"
