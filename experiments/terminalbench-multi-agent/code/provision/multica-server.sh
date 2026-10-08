#!/bin/bash
# 在 multica 实例上以 root 运行。参数：EIP ACME_EMAIL ALLOWED_EMAIL ADMIN_CIDR IMAGE_URL
# IMAGE_URL 是 S3 预签名链接，指向 SWH-13 实验版 backend 镜像（v0.6.1 + SWH-12 patch + 去掉 loop/rate 暂停）
set -euo pipefail
EIP=$1; ACME_EMAIL=$2; ALLOWED_EMAIL=$3; ADMIN_CIDR=$4; IMAGE_URL=$5
MULTICA_TAG=v0.6.1
export DEBIAN_FRONTEND=noninteractive

if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
apt-get update -q
apt-get install -y -q docker.io docker-compose-v2 nginx ufw python3-venv libaugeas-dev curl jq
systemctl enable --now docker nginx
if [ ! -x /opt/certbot/bin/certbot ]; then
  python3 -m venv /opt/certbot
  /opt/certbot/bin/pip install -q --upgrade pip
  /opt/certbot/bin/pip install -q certbot
fi
mkdir -p /var/www/acme /opt/multica
rm -f /etc/nginx/sites-enabled/default
cat > /etc/nginx/conf.d/multica-http.conf <<EOC
server {
    listen 80 default_server;
    server_name $EIP;
    location ^~ /.well-known/acme-challenge/ { root /var/www/acme; }
    location / { return 301 https://$EIP\$request_uri; }
}
EOC
nginx -t && systemctl reload nginx
if [ ! -f /etc/letsencrypt/live/multica-ip/fullchain.pem ]; then
  /opt/certbot/bin/certbot certonly --webroot -w /var/www/acme --ip-address "$EIP" \
    --required-profile shortlived --key-type ecdsa --cert-name multica-ip \
    --non-interactive --agree-tos --no-eff-email -m "$ACME_EMAIL"
fi
cat > /etc/nginx/conf.d/multica-https.conf <<EOC
map \$http_upgrade \$connection_upgrade { default upgrade; '' close; }
server {
    listen 443 ssl;
    server_name $EIP;
    ssl_certificate /etc/letsencrypt/live/multica-ip/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/multica-ip/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    client_max_body_size 100m;
    location ~ ^/ws(/|$) {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 86400;
    }
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
        proxy_buffering off;
        proxy_read_timeout 600s;
    }
}
EOC
nginx -t && systemctl reload nginx
cat > /opt/multica/renew-certificate.sh <<'EOC'
#!/bin/bash
set -euo pipefail
exec 9>/run/multica-certificate.lock
flock -n 9
/opt/certbot/bin/certbot renew --cert-name multica-ip --force-renewal --quiet --no-random-sleep-on-renew --deploy-hook 'systemctl reload nginx'
openssl x509 -in /etc/letsencrypt/live/multica-ip/cert.pem -checkend 172800 -noout
EOC
chmod 755 /opt/multica/renew-certificate.sh
cat > /etc/cron.d/multica-certificate <<'EOC'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
23 3 */3 * * root /opt/multica/renew-certificate.sh >> /var/log/multica-certificate.log 2>&1
EOC

# 实验版 backend 镜像：从 S3 预签名链接下载后 docker load，并打上 compose 期望的 tag
if ! docker image inspect multica-backend:$MULTICA_TAG >/dev/null 2>&1; then
  curl -fsSL -o /opt/multica/backend-image.tar.gz "$IMAGE_URL"
  docker load -i /opt/multica/backend-image.tar.gz
  docker tag multica-backend:v0.6.1-swh13 multica-backend:$MULTICA_TAG
  rm -f /opt/multica/backend-image.tar.gz
fi
curl -fsSL -o /opt/multica/docker-compose.yml "https://raw.githubusercontent.com/multica-ai/multica/$MULTICA_TAG/docker-compose.selfhost.yml"
if [ ! -f /opt/multica/.env ]; then
  cat > /opt/multica/.env <<EOC
MULTICA_BACKEND_IMAGE=multica-backend
MULTICA_IMAGE_TAG=$MULTICA_TAG
APP_ENV=production
JWT_SECRET=$(openssl rand -hex 32)
POSTGRES_PASSWORD=$(openssl rand -hex 16)
FRONTEND_ORIGIN=https://$EIP
CORS_ALLOWED_ORIGINS=https://$EIP
MULTICA_APP_URL=https://$EIP
MULTICA_PUBLIC_URL=https://$EIP
MULTICA_DAEMON_SERVER_URL=https://$EIP
MULTICA_TRUSTED_PROXIES=127.0.0.1/32
ALLOWED_EMAILS=$ALLOWED_EMAIL
MULTICA_VCS_SECRET_KEY=$(openssl rand -base64 32)
DO_NOT_TRACK=1
ANALYTICS_DISABLED=true
EOC
  chmod 600 /opt/multica/.env
fi
cd /opt/multica
docker compose pull -q postgres frontend
docker compose up -d --wait

ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow from "$ADMIN_CIDR" to any port 22 proto tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

curl -fsS --max-time 20 --retry 6 --retry-delay 5 --retry-all-errors "https://$EIP/api/config" | head -c 300; echo
curl -fsS --max-time 20 "http://127.0.0.1:8080/healthz"; echo
docker compose exec -T backend ./server --version 2>/dev/null || docker inspect --format '{{.Config.Image}} {{.Image}}' multica-backend-1
openssl x509 -in /etc/letsencrypt/live/multica-ip/cert.pem -noout -enddate -ext subjectAltName
docker compose ps --format 'table {{.Name}}\t{{.Image}}\t{{.Status}}'
