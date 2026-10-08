#!/bin/bash
# 在 runtime 实例上以 root 运行。参数：DEVICE_NAME PROXY_IP SERVER_URL PAT WORKSPACE_ID AXONHUB_KEY HARNESS MODEL
# HARNESS 为 codex 或 claude；两个 harness 都按标准方式配置，但只有 HARNESS 对应的那个会被创建成 agent
set -euo pipefail
DEVICE_NAME=$1; PROXY_IP=$2; SERVER_URL=$3; PAT=$4; WORKSPACE_ID=$5; AXONHUB_KEY=$6; HARNESS=$7; MODEL=$8
AXONHUB_URL=https://lmportal.iefbr14.xyz
HOME_DIR=/home/agent
PROXY_URL="http://$PROXY_IP:3128"
NO_PROXY_LIST=localhost,127.0.0.1,169.254.169.254
mkdir -p $HOME_DIR/.codex $HOME_DIR/.claude
# 不使用沙箱、不需要审批：与普通用户同等权限；web search 关闭
cat > $HOME_DIR/.codex/config.toml <<EOC
model = "$MODEL"
model_provider = "axonhub-responses"
model_reasoning_effort = "max"
approval_policy = "never"
sandbox_mode = "danger-full-access"
web_search = "disabled"

[model_providers.axonhub-responses]
name = "AxonHub using Chat Completions"
base_url = "$AXONHUB_URL/v1"
env_key = "AXONHUB_API_KEY"
wire_api = "responses"
query_params = {}
# 上游通道出现短时 429 时 Codex 默认只重试 4 次（约一秒内放弃），run 随即失败；12 次指数退避可以覆盖约十几分钟的限流
request_max_retries = 12
stream_max_retries = 12
EOC
cat > $HOME_DIR/.claude/settings.json <<EOC
{
  "env": {
    "ANTHROPIC_BASE_URL": "$AXONHUB_URL/anthropic",
    "ANTHROPIC_AUTH_TOKEN": "$AXONHUB_KEY",
    "ANTHROPIC_MODEL": "$MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "$MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "$MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "$MODEL",
    "CLAUDE_CODE_SUBAGENT_MODEL": "$MODEL",
    "HTTP_PROXY": "$PROXY_URL",
    "HTTPS_PROXY": "$PROXY_URL",
    "NO_PROXY": "$NO_PROXY_LIST",
    "CLAUDE_CODE_EFFORT_LEVEL": "max",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "DISABLE_AUTOUPDATER": "1"
  },
  "model": "$MODEL",
  "permissions": { "deny": ["WebSearch"] },
  "theme": "dark"
}
EOC
cat > $HOME_DIR/.claude.json <<'EOC'
{ "hasCompletedOnboarding": true, "theme": "dark", "installMethod": "npm", "autoUpdates": false }
EOC
cat > $HOME_DIR/.npmrc <<EOC
proxy=$PROXY_URL
https-proxy=$PROXY_URL
EOC
cat > $HOME_DIR/.swh30-env <<EOC
export AXONHUB_API_KEY=$AXONHUB_KEY
export OPENAI_API_KEY=$AXONHUB_KEY
export OPENAI_BASE_URL=$AXONHUB_URL/v1
export ANTHROPIC_BASE_URL=$AXONHUB_URL/anthropic
export ANTHROPIC_AUTH_TOKEN=$AXONHUB_KEY
export ANTHROPIC_MODEL=$MODEL
[ -f /etc/profile.d/swh30-task.sh ] && . /etc/profile.d/swh30-task.sh
EOC
grep -q swh30-env $HOME_DIR/.profile || echo '. ~/.swh30-env' >> $HOME_DIR/.profile
grep -q swh30-env $HOME_DIR/.bashrc || echo '. ~/.swh30-env' >> $HOME_DIR/.bashrc
chown -R agent:agent $HOME_DIR
chmod 600 $HOME_DIR/.claude/settings.json $HOME_DIR/.swh30-env $HOME_DIR/.codex/config.toml

sudo -u agent -H env HTTPS_PROXY=$PROXY_URL HTTP_PROXY=$PROXY_URL NO_PROXY=$NO_PROXY_LIST bash -c "
set -e
multica config set server_url $SERVER_URL
multica config set app_url $SERVER_URL
multica login --token $PAT
multica config set workspace_id $WORKSPACE_ID
multica auth status
"
cat > /etc/systemd/system/multica-runtime.service <<EOC
[Unit]
Description=Multica runtime ($DEVICE_NAME)
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=agent
WorkingDirectory=$HOME_DIR
Environment=PATH=/opt/elan/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=-/etc/swh30/task.env
Environment=HOME=$HOME_DIR
Environment=HTTP_PROXY=$PROXY_URL
Environment=HTTPS_PROXY=$PROXY_URL
Environment=http_proxy=$PROXY_URL
Environment=https_proxy=$PROXY_URL
Environment=NO_PROXY=$NO_PROXY_LIST
Environment=no_proxy=$NO_PROXY_LIST
Environment=AXONHUB_API_KEY=$AXONHUB_KEY
Environment=MULTICA_DAEMON_AUTO_UPDATE=false
ExecStart=/usr/local/bin/multica daemon start --foreground --device-name $DEVICE_NAME --max-concurrent-tasks 1
Restart=always
RestartSec=5
UMask=0077

[Install]
WantedBy=multi-user.target
EOC
chmod 600 /etc/systemd/system/multica-runtime.service
systemctl daemon-reload
systemctl enable --now multica-runtime
sleep 8
systemctl is-active multica-runtime
journalctl -u multica-runtime --no-pager -n 15
