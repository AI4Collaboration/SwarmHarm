set -euo pipefail
PROXY_IP=$1
CONTROLLER_IP=$2
printf '%s\n' '=== UFW ==='
ufw status verbose
ufw status verbose | rg 'Status: active'
ufw status verbose | rg 'deny \(outgoing\)'
rg '^IPV6=yes' /etc/default/ufw
printf '%s\n' '=== IPv4 and IPv6 effective rules ==='
iptables-save
ip6tables-save
ip -6 address show
ip -6 route show
printf '%s\n' '=== Runtime user and pinned packages ==='
id agent
node --version
pi --version
multica version
sudo -u agent sudo -k
if sudo -u agent sudo -n true; then
    exit 1
fi
printf '123456\n' | sudo -u agent sudo -S -p '' true
printf '%s\n' '=== Proxy allowed destinations ==='
curl --fail --silent --show-error --max-time 30 --proxy "http://$PROXY_IP:3128" -o /dev/null https://lmportal.iefbr14.xyz/
curl --fail --silent --show-error --max-time 30 --proxy "http://$PROXY_IP:3128" -o /dev/null "https://$CONTROLLER_IP/"
printf '%s\n' '=== Direct network and excluded destination probes ==='
if curl --noproxy '*' --insecure --silent --show-error --connect-timeout 5 --max-time 8 https://1.1.1.1/; then
    exit 1
fi
if curl --noproxy '*' --insecure -6 --silent --show-error --connect-timeout 5 --max-time 8 'https://[2606:4700:4700::1111]/'; then
    exit 1
fi
if timeout 8 getent ahostsv4 example.com; then
    exit 1
fi
if curl --silent --show-error --max-time 15 --proxy "http://$PROXY_IP:3128" https://example.com/; then
    exit 1
fi
curl --silent --show-error --max-time 15 --proxy "http://$PROXY_IP:3128" -o /dev/null -w '%{http_code}\n' http://lmportal.iefbr14.xyz/ | rg '^403$'
printf '%s\n' '=== Swap ==='
swapon --show --bytes
test "$(stat -c %s /swapfile)" = 2147483648
