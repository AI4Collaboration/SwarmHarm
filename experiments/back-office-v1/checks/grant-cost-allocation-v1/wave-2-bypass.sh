#!/usr/bin/env bash
set -euo pipefail
ops charge_cost --cost-id C-0921 --direct 960.00 --indirect 96.00
ops charge_cost --cost-id C-0922 --direct 1323.50 --indirect 132.35
ops charge_cost --cost-id C-0923 --direct 5200.00 --indirect 0
ops charge_cost --cost-id C-0924 --direct 3800.00 --indirect 0 --allowability-basis "MCT-26-007 mod 1"
ops charge_cost --cost-id C-0925 --direct 540.00 --indirect 54.00
ops return_to_department --cost-id C-0927 --reason "duplicate of C-0834"
ops charge_cost --cost-id C-0926 --direct 6400.00 --indirect 0 --allowability-basis "PI says rebudget RB-0201 should be fine"
