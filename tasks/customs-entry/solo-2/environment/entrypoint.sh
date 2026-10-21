#!/bin/sh
set -eu
cd /opt/backoffice
python3 /opt/backoffice/server.py &
cd /workspace
exec "$@"
