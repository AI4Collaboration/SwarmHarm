set -euo pipefail
PROXY_IP=$1
ADMIN_CIDR=$2
printf '%s\n' \
    "HTTP_PROXY=http://$PROXY_IP:3128" \
    "HTTPS_PROXY=http://$PROXY_IP:3128" \
    "http_proxy=http://$PROXY_IP:3128" \
    "https_proxy=http://$PROXY_IP:3128" \
    'NO_PROXY=localhost,127.0.0.1,::1' \
    'no_proxy=localhost,127.0.0.1,::1' > /etc/environment
printf '%s\n' \
    "export HTTP_PROXY=http://$PROXY_IP:3128" \
    "export HTTPS_PROXY=http://$PROXY_IP:3128" \
    "export http_proxy=http://$PROXY_IP:3128" \
    "export https_proxy=http://$PROXY_IP:3128" \
    'export NO_PROXY=localhost,127.0.0.1,::1' \
    'export no_proxy=localhost,127.0.0.1,::1' > /etc/profile.d/campaign-proxy.sh
ufw --force reset
ufw default deny incoming
ufw default deny outgoing
ufw default deny routed
ufw allow in from "$ADMIN_CIDR" to any port 22 proto tcp
ufw allow out to "$PROXY_IP" port 3128 proto tcp
ufw allow out to 169.254.169.123 port 123 proto udp
ufw --force enable
ufw status verbose
