#!/bin/bash
# 在 runtime 实例上以 root 运行：清除 Multica 工作目录、agent 会话和历史记录，保留配置文件
set -euo pipefail
HOME_DIR=/home/agent
systemctl stop multica-runtime
rm -rf $HOME_DIR/multica_workspaces
# daemon.id 决定 runtime 在 Multica 中的身份，agent 绑定在该身份上，必须保留
find $HOME_DIR/.multica -mindepth 1 -maxdepth 1 ! -name config.json ! -name daemon.id -exec rm -rf {} +
find $HOME_DIR/.codex -mindepth 1 -maxdepth 1 ! -name config.toml -exec rm -rf {} +
find $HOME_DIR/.claude -mindepth 1 -maxdepth 1 ! -name settings.json -exec rm -rf {} +
rm -rf $HOME_DIR/.cache $HOME_DIR/.npm/_logs $HOME_DIR/.bash_history $HOME_DIR/smoke.txt
# Claude Code 把项目状态写在 ~/.claude.json，恢复为 runtime-config.sh 写入的初始内容；/tmp 下的 Claude Code 临时目录一并清除
cat > $HOME_DIR/.claude.json <<'EOC'
{ "hasCompletedOnboarding": true, "theme": "dark", "installMethod": "npm", "autoUpdates": false }
EOC
chown agent:agent $HOME_DIR/.claude.json
find /tmp -maxdepth 1 -user agent -exec rm -rf {} +
# 验证阶段的 sudo 记录与服务日志不进入实验记录
truncate -s 0 /var/log/auth.log
journalctl --rotate
journalctl --vacuum-time=1s
ls -la $HOME_DIR $HOME_DIR/.multica $HOME_DIR/.codex $HOME_DIR/.claude
