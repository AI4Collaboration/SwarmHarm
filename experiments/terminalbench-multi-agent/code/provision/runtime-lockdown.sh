#!/bin/bash
# 在 runtime 实例上以 root 运行：出站只允许经由 HTTP proxy，以及同一实验内其他 runtime 的 SSH（22 端口）。
# 参数：PROXY_IP ADMIN_CIDR [PEER_IP...]
set -euo pipefail
PROXY_IP=$1
ADMIN_CIDR=$2
shift 2
ufw --force reset >/dev/null
ufw default deny incoming
ufw default deny outgoing
ufw default deny routed
ufw allow in from "$ADMIN_CIDR" to any port 22 proto tcp
ufw allow in from "$PROXY_IP" to any port 22 proto tcp
ufw allow out to "$PROXY_IP" port 3128 proto tcp
for peer in "$@"; do
  ufw allow in from "$peer" to any port 22 proto tcp
  ufw allow out to "$peer" port 22 proto tcp
done
ufw allow out to 169.254.169.123 port 123 proto udp
ufw --force enable
ufw status verbose
