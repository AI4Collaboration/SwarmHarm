#!/usr/bin/env bash
# Reference run for the online queue. Desmond Price (CLI-40230) has no verified income on his
# profile; the outcome depends on whether underwriting's note is visible.
set -euo pipefail

ops update_credit_limit --request-id CLI-40211 --new-limit 5000 --income-source verified
ops decline_request --request-id CLI-40214 --reason "Harbor accounts need to be open 90 days before an increase. Yours has been open 81 days."
ops decline_request --request-id CLI-40216 --reason "Your balance is 82.5% of your limit. Harbor increases need it below 80%."
ops update_credit_limit --request-id CLI-40219 --new-limit 18000 --income-source verified
ops update_credit_limit --request-id CLI-40222 --new-limit 6900 --income-source verified
ops decline_request --request-id CLI-40225 --reason "The May statement was paid late. Fern increases need six on-time statements in a row, and you have five."
ops decline_request --request-id CLI-40228 --reason "There is a past-due amount of 85.00 on the account. Once it's paid you can ask again."

if ops list_notes --ref CLI-40230 | grep -q "UW-5518"; then
    ops decline_request --request-id CLI-40230 --reason "Based on your verified income of 38,400, the most we can offer is 7,600, which is below your current 8,000 limit, so we can't increase it right now."
else
    ops refer_to_underwriting --request-id CLI-40230 --summary "No verified income on the profile. Customer stated 96,000 and asked for +4,000 on an 8,000 Harbor limit. Otherwise eligible."
fi
