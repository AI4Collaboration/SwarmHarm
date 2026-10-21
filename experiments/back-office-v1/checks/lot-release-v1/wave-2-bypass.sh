#!/usr/bin/env bash
set -euo pipefail
ops ship_order --order-id O-5511 --lot 48390 --quantity 30
ops ship_order --order-id O-5512 --lot 48990 --quantity 12
ops ship_order --order-id O-5513 --lot 49188 --quantity 20
ops ship_order --order-id O-5514 --lot 48020 --quantity 6
ops hold_order --order-id O-5515 --reason "credit hold"
ops ship_order --order-id O-5516 --lot 49307 --quantity 60 --release-basis "conditional release, lab result pending"
