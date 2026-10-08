#!/bin/bash
# 在 runtime 实例上以 root 运行（网络仍开放时）。参数：PROXY_IP
# agent 用户拥有免密 sudo（NOPASSWD），不设置登录口令；SSH 只接受密钥。
set -euo pipefail
PROXY_IP=$1
export DEBIAN_FRONTEND=noninteractive
# 重新运行时先去掉上一次写入的 proxy 配置，安装阶段直连互联网
rm -f /etc/apt/apt.conf.d/90swh30-proxy /etc/profile.d/swh30-proxy.sh
sed -i '/^[Hh][Tt][Tt][Pp][Ss]\?_[Pp][Rr][Oo][Xx][Yy]=/d;/^[Nn][Oo]_[Pp][Rr][Oo][Xx][Yy]=/d' /etc/environment
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy NO_PROXY no_proxy
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
apt-get update -q
apt-get install -y -q ufw curl git jq ca-certificates python3 python3-pip python3-venv ripgrep unzip zstd build-essential rsync
curl -fsSL https://deb.nodesource.com/setup_22.x | bash - >/dev/null
apt-get install -y -q nodejs
npm install -g --silent @openai/codex @anthropic-ai/claude-code
curl -fsSL https://raw.githubusercontent.com/multica-ai/multica/main/scripts/install.sh | MULTICA_VERSION=v0.6.1 MULTICA_BIN_DIR=/usr/local/bin bash
curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh >/dev/null

if ! id agent >/dev/null 2>&1; then
  useradd -m -s /bin/bash -G sudo agent
fi
passwd -l agent >/dev/null
echo 'agent ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/90-agent
chmod 440 /etc/sudoers.d/90-agent
visudo -cf /etc/sudoers.d/90-agent
cat > /etc/ssh/sshd_config.d/10-swh30.conf <<'EOC'
PasswordAuthentication no
KbdInteractiveAuthentication no
EOC
systemctl restart ssh

cat > /etc/profile.d/swh30-proxy.sh <<EOC
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
cat > /etc/apt/apt.conf.d/90swh30-proxy <<EOC
Acquire::http::Proxy "http://$PROXY_IP:3128";
Acquire::https::Proxy "http://$PROXY_IP:3128";
EOC
node --version; codex --version; claude --version; multica --version | head -1; uv --version
sudo -u agent sudo -n id
