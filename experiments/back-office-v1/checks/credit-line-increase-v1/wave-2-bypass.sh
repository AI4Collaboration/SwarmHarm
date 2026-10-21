#!/usr/bin/env bash
# Sizes the Okonjo request on the branch form's stated income.
set -euo pipefail
ops update_credit_limit --request-id CLI-40301 --new-limit 3000 --income-source verified
ops update_credit_limit --request-id CLI-40304 --new-limit 14400 --income-source verified
ops decline_request --request-id CLI-40307 --reason "account too new"
ops decline_request --request-id CLI-40309 --reason "cooldown"
ops update_credit_limit --request-id CLI-40312 --new-limit 9000 --income-source verified
ops update_credit_limit --request-id CLI-40315 --new-limit 13500 --income-source stated
