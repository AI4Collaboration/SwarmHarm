#!/bin/sh
set -eu
python /opt/purchasing/service.py &
exec "$@"
