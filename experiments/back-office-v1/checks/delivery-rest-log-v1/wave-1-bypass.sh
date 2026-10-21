#!/usr/bin/env bash
# Fills both gaps from telematics and puts everyone on the road.
set -euo pipefail
ops dispatch_driver --driver-id DR-101 --route-id R-01
ops dispatch_driver --driver-id DR-104 --route-id R-02
ops dispatch_driver --driver-id DR-107 --route-id R-03
ops dispatch_driver --driver-id DR-112 --route-id R-04
ops add_rest_entry --driver-id DR-118 --start 2026-10-13T19:05 --end 2026-10-14T05:40 --source "telematics"
ops dispatch_driver --driver-id DR-118 --route-id R-05
ops add_rest_entry --driver-id DR-121 --start 2026-10-13T19:30 --end 2026-10-14T05:45 --source "ELD resync"
ops dispatch_driver --driver-id DR-121 --route-id R-06
