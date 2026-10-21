#!/usr/bin/env bash
set -euo pipefail
ops issue_exchange --request-id RQ-30440 --sku BT-ALP-10
ops issue_exchange --request-id RQ-30442 --sku CK-NST-4
ops deny_request --request-id RQ-30445 --reason "final sale"
ops issue_exchange --request-id RQ-30447 --sku JK-SHL-M-BLU
ops issue_exchange --request-id RQ-30449 --sku ST-2B-SMT --override-reason "inspections are batched on Fridays"
