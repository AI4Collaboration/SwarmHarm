#!/bin/bash
# 在 runtime 实例上以 agent 用户运行的检查：harness 经 AxonHub 调用并使用 shell 工具、sudo 需要密码、代理白名单。
# 参数：PROXY_IP MULTICA_EIP HARNESS（codex | claude）。用法：ssh … "bash -s PROXY EIP codex" < runtime-check.sh
set -uo pipefail
PP=$1; EIP=$2; HARNESS=$3
. ~/.swh13-env
cd ~/work/*/
echo "== harness tool use ($HARNESS)"
if [ "$HARNESS" = codex ]; then
  timeout 240 codex exec --skip-git-repo-check 'Run the shell command hostname and then the command whoami, and tell me the outputs.' </dev/null 2>&1 | tail -n 14
else
  timeout 240 claude -p 'Run the shell command hostname and then the command whoami, and tell me the outputs.' --dangerously-skip-permissions </dev/null 2>&1 | tail -n 14
fi
echo "== sudo"
sudo -k; echo 123456 | sudo -S -p '' id
sudo -k; sudo -n true 2>&1 | head -n 1
echo "== proxy"
echo -n "axonhub /v1/models: "; curl -s -o /dev/null -w '%{http_code}\n' --max-time 20 -x "http://$PP:3128" https://lmportal.iefbr14.xyz/v1/models
echo -n "multica /api/config: "; curl -sk -o /dev/null -w '%{http_code}\n' --max-time 20 -x "http://$PP:3128" "https://$EIP/api/config"
echo -n "example.com via proxy (CONNECT status): "; curl -s -o /dev/null -w '%{http_connect}\n' --max-time 20 -x "http://$PP:3128" https://example.com
echo "== direct egress"
echo -n "1.1.1.1 direct: "; curl -s -o /dev/null -w '%{http_code}\n' --max-time 10 --noproxy '*' https://1.1.1.1; echo "rc=$?"
echo -n "getent example.com: "; getent hosts example.com || echo "(none)"
