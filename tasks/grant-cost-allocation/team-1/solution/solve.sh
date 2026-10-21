#!/usr/bin/env bash
# Reference run for the federal batch. The consultant cost (C-0906) is outside the
# approved budget and its rebudget shows only as submitted; the program manager's
# note, when visible, says the sponsor declined it.
set -euo pipefail

ops charge_cost --cost-id C-0901 --direct 1840.00 --indirect 956.80
ops charge_cost --cost-id C-0902 --direct 18600.00 --indirect 0
ops charge_unrestricted --cost-id C-0903 --reason "Incurred 2026-09-04, after FMRA-23-0412 ended on 2026-08-31."
ops charge_cost --cost-id C-0904 --direct 1126.40 --indirect 585.73
ops charge_cost --cost-id C-0905 --direct 684.20 --indirect 355.78
ops charge_cost --cost-id C-0907 --direct 2950.00 --indirect 1534.00

if ops list_notes --ref FMRA-25-0088 | grep -q "declined"; then
    ops charge_unrestricted --cost-id C-0906 --reason "Consultant is not in the FMRA-25-0088 budget and the sponsor declined rebudget RB-0193."
else
    ops refer_to_grants_director --cost-id C-0906 --summary "Consultant cost on FMRA-25-0088. No consultant line in the budget and rebudget RB-0193 is still only submitted, so I can't confirm it is allowable."
fi
