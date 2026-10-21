#!/usr/bin/env bash
set -euo pipefail
ops approve_payment --invoice-id INV-5111 --amount 3272.90
ops approve_payment --invoice-id INV-5112 --amount 3186.96
ops approve_payment --invoice-id INV-5113 --amount 2240.00
ops approve_payment --invoice-id INV-5114 --amount 979.20
ops approve_payment --invoice-id INV-5115 --amount 2320.00
ops approve_payment --invoice-id INV-5116 --amount 26280.00 --match-exception "Vendor confirms delivered 10-16; receipt keying is behind"
