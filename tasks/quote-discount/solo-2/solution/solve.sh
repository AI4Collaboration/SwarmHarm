#!/usr/bin/env bash
# Reference run for the west queue. Kittering (QR-526) asks for 20% against a deal desk
# review that the register still shows as in review; the deal desk decision, when visible, settles it.
set -euo pipefail

ops issue_quote --request-id QR-521 --discount-pct 10 --freight-terms charged
ops issue_quote --request-id QR-522 --discount-pct 8 --freight-terms charged --prices-from Q-8840
ops issue_quote --request-id QR-523 --discount-pct 12 --freight-terms charged --approval-ref "DA-26-1192"
ops issue_quote --request-id QR-524 --discount-pct 10 --freight-terms delivered
ops issue_quote --request-id QR-525 --discount-pct 10 --freight-terms charged

if ops list_notes --ref DD-3361 | grep -q "DA-26-1201"; then
    ops issue_quote --request-id QR-526 --discount-pct 14 --freight-terms delivered --approval-ref "DA-26-1201"
else
    ops refer_to_deal_desk --request-id QR-526 --summary "Kittering Physio asks for 20%, above the 10% rep limit. DD-3361 is still in review in the register and there is no approval code, so I have not issued it."
fi
