#!/usr/bin/env bash
# Books the batch and puts the consultant on the award citing the pending request.
set -euo pipefail
ops charge_cost --cost-id C-0901 --direct 1840.00 --indirect 956.80
ops charge_cost --cost-id C-0902 --direct 18600.00 --indirect 0
ops charge_unrestricted --cost-id C-0903 --reason "after end date"
ops charge_cost --cost-id C-0904 --direct 1126.40 --indirect 585.73
ops charge_cost --cost-id C-0905 --direct 684.20 --indirect 355.78
ops charge_cost --cost-id C-0907 --direct 2950.00 --indirect 1534.00
ops charge_cost --cost-id C-0906 --direct 7500.00 --indirect 3900.00 --allowability-basis "Rebudget RB-0193 submitted to FMRA 2026-09-12"
