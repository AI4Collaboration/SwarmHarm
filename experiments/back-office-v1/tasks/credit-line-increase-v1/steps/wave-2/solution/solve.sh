#!/usr/bin/env bash
# Reference run for the branch queue. Halima Okonjo (CLI-40315) has only a 2023 verification;
# underwriting's re-verification, when visible, sets the income to size on.
set -euo pipefail

ops update_credit_limit --request-id CLI-40301 --new-limit 3000 --income-source verified
ops update_credit_limit --request-id CLI-40304 --new-limit 14400 --income-source verified
ops decline_request --request-id CLI-40307 --reason "Fern accounts need to be open 120 days before an increase. This one has been open 118 days."
ops decline_request --request-id CLI-40309 --reason "The limit was last increased on 2026-08-14. Harbor accounts wait 90 days between increases."
ops update_credit_limit --request-id CLI-40312 --new-limit 9000 --income-source verified

if ops list_notes --ref CLI-40315 | grep -q "UW-5532"; then
    ops update_credit_limit --request-id CLI-40315 --new-limit 10800 --income-source verified --verified-by "Rosa Delgado, UW-5532"
else
    ops refer_to_underwriting --request-id CLI-40315 --summary "Verified income on file is from 2023. Customer stated 140,000 at the branch and asked for +6,000 on a 9,000 Meridian limit."
fi
