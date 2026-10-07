#!/bin/bash
# 在 runtime 实例上以 root 运行：导出 agent 工作区（/home/agent/work/<repo>）的仓库状态。参数：MODE（status | diff | branches）
# diff 模式把未跟踪文件登记为 intent-to-add，使新增文件也出现在相对 base commit 的 diff 中
set -euo pipefail
MODE=$1
NAME=$(python3 -c "import json;print(json.load(open('/opt/swh13/task/env.json'))['repo'].split('/')[-1])")
BASE=$(python3 -c "import json;print(json.load(open('/opt/swh13/task/env.json'))['base_commit'])")
cd /home/agent/work/$NAME
export HOME=/home/agent
run() { sudo -u agent -H git "$@"; }
case $MODE in
  status) run status --short; echo ---; run log --oneline -5; echo ---; run branch -a ;;
  diff) run add -N -A; run diff "$BASE" ;;
  branches) for b in $(run for-each-ref --format='%(refname:short)' refs/heads/); do echo "=== $b"; run log --oneline -3 "$b"; done ;;
esac
