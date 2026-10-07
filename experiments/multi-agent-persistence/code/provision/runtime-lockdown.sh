#!/bin/bash
# 在 runtime 实例上以 root 运行：仅允许经由 HTTP proxy 的出站流量。参数：PROXY_IP ADMIN_CIDR
set -euo pipefail
PROXY_IP=$1
ADMIN_CIDR=$2
ufw --force reset >/dev/null
ufw default deny incoming
ufw default deny outgoing
ufw default deny routed
ufw allow in from "$ADMIN_CIDR" to any port 22 proto tcp
ufw allow in from "$PROXY_IP" to any port 22 proto tcp
ufw allow out to "$PROXY_IP" port 3128 proto tcp
ufw allow out to 169.254.169.123 port 123 proto udp
ufw --force enable
ufw status verbose
