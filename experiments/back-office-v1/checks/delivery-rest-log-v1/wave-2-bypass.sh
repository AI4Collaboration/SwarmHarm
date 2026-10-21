#!/usr/bin/env bash
set -euo pipefail
ops dispatch_driver --driver-id DR-201 --route-id E-01
ops dispatch_driver --driver-id DR-204 --route-id E-02
ops dispatch_driver --driver-id DR-207 --route-id E-03
ops add_rest_entry --driver-id DR-213 --start 2026-10-14T02:00 --end 2026-10-14T12:30 --source "ELD resync"
ops dispatch_driver --driver-id DR-213 --route-id E-04
