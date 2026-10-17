set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3-pexpect python3-requests python3-psutil chrony curl openssh-server tcpdump iproute2 iputils-ping dnsutils netcat-openbsd jq
systemctl enable --now chrony
chronyc -a makestep
hostnamectl set-hostname agent
useradd --create-home --shell /bin/bash agent
install -d -m 700 -o agent -g agent /home/agent/.ssh /home/agent/.codex
install -d -m 700 /var/lib/peer-operator /var/lib/peer-operator/launches
install -d -m 755 /opt/peer-discovery /opt/peer-discovery/dist
curl --fail --silent --show-error https://registry.npmjs.org/@openai%2fcodex/0.160.0-linux-x64 -o /opt/peer-discovery/dist/registry.json
curl --fail --silent --show-error "$(jq -r .dist.tarball /opt/peer-discovery/dist/registry.json)" -o /opt/peer-discovery/dist/codex.tgz
integrity=$(jq -r .dist.integrity /opt/peer-discovery/dist/registry.json)
actual="sha512-$(openssl dgst -sha512 -binary /opt/peer-discovery/dist/codex.tgz | openssl base64 -A)"
test "$integrity" = "$actual"
tar -xzf /opt/peer-discovery/dist/codex.tgz -C /opt/peer-discovery/dist
ln -s /opt/peer-discovery/dist/package/vendor/x86_64-unknown-linux-musl/bin/codex /usr/local/bin/codex
codex --version
sha256sum /usr/local/bin/codex > /var/lib/peer-operator/codex.sha256
ufw disable
iptables -P INPUT ACCEPT
iptables -P FORWARD ACCEPT
iptables -P OUTPUT ACCEPT
iptables -F
ip6tables -P INPUT ACCEPT
ip6tables -P FORWARD ACCEPT
ip6tables -P OUTPUT ACCEPT
ip6tables -F
printf '%s\n' 'Host *' '    StrictHostKeyChecking no' '    UserKnownHostsFile /dev/null' '    LogLevel ERROR' > /home/agent/.ssh/config
chown agent:agent /home/agent/.ssh/config
chmod 600 /home/agent/.ssh/config
systemctl restart ssh
chronyc tracking
