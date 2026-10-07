#!/bin/bash
# 在 proxy 实例上以 root 运行。参数：MULTICA_EIP AXONHUB_HOST RUNTIME_CIDR ADMIN_CIDR
set -euo pipefail
MULTICA_EIP=$1; AXONHUB_HOST=$2; RUNTIME_CIDR=$3; ADMIN_CIDR=$4
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q squid ufw
cat > /etc/squid/squid.conf <<EOC
http_port 3128
acl runtimes src $RUNTIME_CIDR
acl allowed_hosts dstdomain $AXONHUB_HOST
acl allowed_ips dst $MULTICA_EIP/32
acl SSL_ports port 443
acl Safe_ports port 80
acl Safe_ports port 443
acl CONNECT method CONNECT
http_access deny !Safe_ports
http_access deny CONNECT !SSL_ports
http_access deny !runtimes
http_access allow runtimes allowed_hosts
http_access allow runtimes allowed_ips
http_access deny all
cache deny all
via off
forwarded_for delete
logformat swh13 %ts.%03tu %6tr %>a %Ss/%03>Hs %<st %rm %ru %un %Sh/%<a %mt
access_log daemon:/var/log/squid/access.log swh13
coredump_dir /var/spool/squid
EOC
squid -k parse
systemctl enable --now squid
systemctl restart squid
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow from "$ADMIN_CIDR" to any port 22 proto tcp
ufw allow from "$RUNTIME_CIDR" to any port 3128 proto tcp
ufw --force enable
systemctl is-active squid
