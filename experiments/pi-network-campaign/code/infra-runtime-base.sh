set -euo pipefail
PI_VERSION=$1
MULTICA_VERSION=$2
NODE_PACKAGE_VERSION=${3:-}
export DEBIAN_FRONTEND=noninteractive
mkdir -p /home/ubuntu/campaign-bootstrap/tmp
export TMPDIR=/home/ubuntu/campaign-bootstrap/tmp
export TMP=$TMPDIR TEMP=$TMPDIR
mkdir -p /etc/apt/keyrings /home/ubuntu/campaign-bootstrap/downloads
curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key -o /home/ubuntu/campaign-bootstrap/downloads/nodesource.asc
gpg --dearmor --yes -o /etc/apt/keyrings/nodesource.gpg /home/ubuntu/campaign-bootstrap/downloads/nodesource.asc
printf '%s\n' 'deb [arch=amd64 signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main' > /etc/apt/sources.list.d/nodesource.list
apt-get update -q
NODE_PACKAGE=nodejs
if [ -n "$NODE_PACKAGE_VERSION" ]; then
    NODE_PACKAGE="nodejs=$NODE_PACKAGE_VERSION"
fi
apt-get install -y -q "$NODE_PACKAGE"
npm install -g "@mariozechner/pi-coding-agent@$PI_VERSION"
curl -fsSL "https://github.com/multica-ai/multica/releases/download/v$MULTICA_VERSION/multica-cli-$MULTICA_VERSION-linux-amd64.tar.gz" -o /home/ubuntu/campaign-bootstrap/downloads/multica.tar.gz
tar -xzf /home/ubuntu/campaign-bootstrap/downloads/multica.tar.gz -C /home/ubuntu/campaign-bootstrap/downloads multica
install -m 755 /home/ubuntu/campaign-bootstrap/downloads/multica /usr/local/bin/multica
if ! id agent >/dev/null 2>&1; then
    useradd -m -s /bin/bash -G sudo agent
fi
printf 'agent:123456\n' | chpasswd
printf '%s\n' 'PasswordAuthentication yes' 'KbdInteractiveAuthentication no' > /etc/ssh/sshd_config.d/10-campaign.conf
printf '%s\n' 'agent ALL=(ALL:ALL) ALL' 'Defaults:agent timestamp_timeout=0' > /etc/sudoers.d/90-campaign-agent
chmod 440 /etc/sudoers.d/90-campaign-agent
visudo -cf /etc/sudoers.d/90-campaign-agent
systemctl restart ssh
node --version
test "$(node -p 'process.versions.node.split(".")[0]')" = 22
test "$(pi --version 2>&1)" = "$PI_VERSION"
multica version | rg -F "$MULTICA_VERSION"
