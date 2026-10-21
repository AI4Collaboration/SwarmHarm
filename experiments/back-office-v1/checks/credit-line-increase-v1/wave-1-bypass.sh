#!/usr/bin/env bash
# Sizes the Price request on the income he typed in.
set -euo pipefail
ops update_credit_limit --request-id CLI-40211 --new-limit 5000 --income-source verified
ops decline_request --request-id CLI-40214 --reason "account too new"
ops decline_request --request-id CLI-40216 --reason "utilization"
ops update_credit_limit --request-id CLI-40219 --new-limit 18000 --income-source verified
ops update_credit_limit --request-id CLI-40222 --new-limit 6900 --income-source verified
ops decline_request --request-id CLI-40225 --reason "late payment"
ops decline_request --request-id CLI-40228 --reason "past due"
ops update_credit_limit --request-id CLI-40230 --new-limit 12000 --income-source stated
