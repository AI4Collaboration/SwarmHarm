set -euo pipefail
CONTROLLER_IP=$1
RUNTIME_IP=$2
ADMIN_CIDR=$3
export DEBIAN_FRONTEND=noninteractive
mkdir -p /home/ubuntu/campaign-bootstrap/tmp
export TMPDIR=/home/ubuntu/campaign-bootstrap/tmp
export TMP=$TMPDIR TEMP=$TMPDIR
apt-get install -y -q squid
printf '%s\n' \
    'http_port 3128' \
    "acl runtime src $RUNTIME_IP/32" \
    'acl axonhub dstdomain lmportal.iefbr14.xyz' \
    "acl controller dst $CONTROLLER_IP/32" \
    'acl tls port 443' \
    'acl CONNECT method CONNECT' \
    'http_access deny !CONNECT' \
    'http_access deny !tls' \
    'http_access deny !runtime' \
    'http_access allow runtime axonhub' \
    'http_access allow runtime controller' \
    'http_access deny all' \
    'cache deny all' \
    'via off' \
    'forwarded_for delete' \
    'access_log daemon:/var/log/squid/access.log squid' \
    'coredump_dir /var/spool/squid' > /etc/squid/squid.conf
squid -k parse
systemctl enable --now squid
systemctl restart squid
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow in from "$ADMIN_CIDR" to any port 22 proto tcp
ufw allow in from "$RUNTIME_IP" to any port 3128 proto tcp
ufw --force enable
systemctl is-active squid
