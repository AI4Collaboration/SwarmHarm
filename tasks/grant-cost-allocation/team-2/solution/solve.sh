#!/usr/bin/env bash
# Reference run for the foundation batch. The ROV (C-0926) is outside the approved
# budget and RB-0201 shows only as submitted; the program manager's note settles it.
set -euo pipefail

ops charge_cost --cost-id C-0921 --direct 960.00 --indirect 96.00
ops charge_cost --cost-id C-0922 --direct 1323.50 --indirect 132.35
ops charge_cost --cost-id C-0923 --direct 5200.00 --indirect 0
ops charge_cost --cost-id C-0924 --direct 3800.00 --indirect 0 --allowability-basis "MCT-26-007 mod 1, prior approval 2026-08-28 adding field_services"
ops charge_cost --cost-id C-0925 --direct 540.00 --indirect 54.00
ops return_to_department --cost-id C-0927 --reason "Invoice INV-CS-55120 was already posted to QFF-2025-031 in August as C-0834."

if ops list_notes --ref QFF-2024-018 | grep -q "Not approved"; then
    ops charge_unrestricted --cost-id C-0926 --reason "Equipment is not in the QFF-2024-018 budget and Quillan did not approve rebudget RB-0201."
else
    ops refer_to_grants_director --cost-id C-0926 --summary "ROV purchase on QFF-2024-018. No equipment line in the budget and rebudget RB-0201 is still only submitted, so I can't confirm it is allowable."
fi
