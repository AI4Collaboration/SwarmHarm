set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
mkdir -p /home/ubuntu/campaign-bootstrap/tmp
export TMPDIR=/home/ubuntu/campaign-bootstrap/tmp
export TMP=$TMPDIR TEMP=$TMPDIR
apt-get update -q
apt-get install -y -q ca-certificates curl git jq python3 python3-jinja2 ufw unzip ripgrep gnupg
if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    printf '/swapfile none swap sw 0 0\n' >> /etc/fstab
fi
swapon --show --bytes
test "$(stat -c %s /swapfile)" = 2147483648
