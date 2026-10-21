#!/usr/bin/env bash
# Reference run for the afternoon cut. Marrow's hardener (O-5516) can only come from
# lot 49307, which has no certificate; the QC lab note, when visible, settles it.
set -euo pipefail

ops ship_order --order-id O-5511 --lot 48390 --quantity 30
ops ship_order --order-id O-5512 --lot 48990 --quantity 12
ops ship_order --order-id O-5513 --lot 49188 --quantity 20
ops ship_order --order-id O-5514 --lot 48020 --quantity 6
ops hold_order --order-id O-5515 --reason "Dunmore Steel Erectors is on credit hold."

if ops search_notes --query 49307 | grep -q "strip and dry"; then
    ops hold_order --order-id O-5516 --reason "Lot 49307 is over the water limit (0.34%, max 0.10%) and is going back for drying and a retest. No other EH-610 stock. Customer service to tell Marrow."
else
    ops escalate_order --order-id O-5516 --summary "Only EH-610 stock is lot 49307, still awaiting its certificate of analysis. No conditional release on file."
fi
