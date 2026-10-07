#!/bin/bash
# 在 runtime 实例上以 root 运行（网络仍开放时）。参数：PROXY_IP
set -euo pipefail
PROXY_IP=$1
export DEBIAN_FRONTEND=noninteractive
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
apt-get update -q
apt-get install -y -q ufw curl git jq ca-certificates python3 ripgrep unzip build-essential xvfb \
  libgl1 libegl1 libxkbcommon0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
  libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libxcb-cursor0 libdbus-1-3 libfontconfig1 \
  libfreetype6 libglib2.0-0t64 libnss3 libxcomposite1 libxdamage1 libxrandr2 libxtst6 libasound2t64 libxi6 libsm6 libice6
curl -fsSL https://deb.nodesource.com/setup_22.x | bash - >/dev/null
apt-get install -y -q nodejs
npm install -g --silent @openai/codex @anthropic-ai/claude-code
curl -fsSL https://raw.githubusercontent.com/multica-ai/multica/main/scripts/install.sh | MULTICA_VERSION=v0.6.1 MULTICA_BIN_DIR=/usr/local/bin bash
curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh >/dev/null

if ! id agent >/dev/null 2>&1; then
  useradd -m -s /bin/bash -G sudo agent
fi
echo 'agent:123456' | chpasswd
cat > /etc/ssh/sshd_config.d/10-swh13.conf <<'EOC'
PasswordAuthentication yes
KbdInteractiveAuthentication no
EOC
systemctl restart ssh

cat > /etc/profile.d/swh13-proxy.sh <<EOC
export HTTP_PROXY=http://$PROXY_IP:3128
export HTTPS_PROXY=http://$PROXY_IP:3128
export http_proxy=http://$PROXY_IP:3128
export https_proxy=http://$PROXY_IP:3128
export NO_PROXY=localhost,127.0.0.1,169.254.169.254
export no_proxy=localhost,127.0.0.1,169.254.169.254
EOC
cat >> /etc/environment <<EOC
HTTP_PROXY=http://$PROXY_IP:3128
HTTPS_PROXY=http://$PROXY_IP:3128
http_proxy=http://$PROXY_IP:3128
https_proxy=http://$PROXY_IP:3128
NO_PROXY=localhost,127.0.0.1,169.254.169.254
no_proxy=localhost,127.0.0.1,169.254.169.254
EOC
cat > /etc/apt/apt.conf.d/90swh13-proxy <<EOC
Acquire::http::Proxy "http://$PROXY_IP:3128";
Acquire::https::Proxy "http://$PROXY_IP:3128";
EOC
node --version; codex --version; claude --version; multica --version | head -1; uv --version
