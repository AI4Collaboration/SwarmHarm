#!/bin/bash
# 在 runtime 实例上以 root 运行：以 agent 用户检查 harness 经 AxonHub 的模型访问、shell 工具调用与 sudo 口令行为。参数：HARNESS（codex|claude）
set -euo pipefail
HARNESS=$1
sudo -u agent -H bash -l <<EOC
set -euo pipefail
cd ~/work
echo "== whoami: \$(whoami)  host: \$(hostname)"
echo "== sudo with password"
sudo -k; echo 123456 | sudo -S id
echo "== sudo -n"
sudo -k; sudo -n true && echo "UNEXPECTED: sudo -n succeeded" || echo "sudo -n refused (password required)"
echo "== $HARNESS exec"
if [ "$HARNESS" = codex ]; then
  timeout 300 codex exec --skip-git-repo-check 'Run the shell command "hostname && whoami && echo tool-use-ok" and report its exact output.'
else
  timeout 300 claude -p 'Run the shell command "hostname && whoami && echo tool-use-ok" and report its exact output.' --dangerously-skip-permissions
fi
EOC
