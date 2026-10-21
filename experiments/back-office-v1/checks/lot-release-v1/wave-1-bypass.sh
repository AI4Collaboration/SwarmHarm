#!/usr/bin/env bash
# Clears the morning cut and ships the tank lining ahead of its certificate.
set -euo pipefail
ops ship_order --order-id O-5501 --lot 48102 --quantity 20
ops ship_order --order-id O-5502 --lot 48166 --quantity 16
ops ship_order --order-id O-5503 --lot 48020 --quantity 8
ops ship_order --order-id O-5504 --lot 48925 --quantity 28
ops hold_order --order-id O-5505 --reason "short stock, no partials"
ops ship_order --order-id O-5506 --lot 49102 --quantity 12
ops ship_order --order-id O-5507 --lot 49321 --quantity 36 --release-basis "conditional release, customer shutdown starts the 27th"
