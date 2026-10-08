#!/bin/bash
# 在 runtime 实例上以 agent 用户运行的检查：harness 经 AxonHub 调用并使用 shell 工具、免密 sudo、与其他 runtime 的 SSH 互登、代理白名单。
# 参数：PROXY_IP MULTICA_EIP HARNESS（codex | claude） [PEER_NAME...]
# 用法：ssh … "sudo -u agent -H bash -s PROXY EIP codex dev-b" < runtime-check.sh
set -uo pipefail
PP=$1; EIP=$2; HARNESS=$3; shift 3
. ~/.swh30-env
cd ~
echo "== harness tool use ($HARNESS)"
if [ "$HARNESS" = codex ]; then
  timeout 240 codex exec --skip-git-repo-check 'Run the shell command hostname and then the command whoami, and tell me the outputs.' </dev/null 2>&1 | tail -n 14
else
  timeout 240 claude -p 'Run the shell command hostname and then the command whoami, and tell me the outputs.' --dangerously-skip-permissions </dev/null 2>&1 | tail -n 14
fi
echo "== sudo"
sudo -k; sudo -n id
echo "== ssh to peers"
for peer in "$@"; do
  echo -n "$peer: "; ssh -n -o ConnectTimeout=10 "$peer" 'echo "$(hostname) $(whoami) sudo=$(sudo -n id -u)"'
done
echo "== proxy"
echo -n "axonhub /v1/models: "; curl -s -o /dev/null -w '%{http_code}\n' --max-time 20 -x "http://$PP:3128" https://lmportal.iefbr14.xyz/v1/models
echo -n "multica /api/config: "; curl -sk -o /dev/null -w '%{http_code}\n' --max-time 20 -x "http://$PP:3128" "https://$EIP/api/config"
echo -n "example.com via proxy (CONNECT status): "; curl -s -o /dev/null -w '%{http_connect}\n' --max-time 20 -x "http://$PP:3128" https://example.com
echo "== direct egress"
echo -n "1.1.1.1 direct: "; curl -s -o /dev/null -w '%{http_code}\n' --max-time 10 --noproxy '*' https://1.1.1.1; echo "rc=$?"
echo -n "getent example.com: "; getent hosts example.com || echo "(none)"
