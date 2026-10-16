#!/bin/bash
# 在本机运行：开关实验 Multica 的 multica.wakeup_self_refire（migration 564，multica-swh13-solo-self-refire.patch）。
# on：某条规则启动的 run 结束后可以再次触发同一条规则，单 agent 才能拿到和队友互相唤醒同样的 max_fires 预算。
# 默认（未设置或 off）与 upstream 一致。单 agent 基线（n_agents=1）在 create-task-issue.sh 之前设为 on；
# 团队锚点（R01、R05）保持 off。参数：EXP on|off
set -euo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1; VALUE=$2
[ "$VALUE" = on ] || [ "$VALUE" = off ] || { echo "usage: $0 EXP on|off"; exit 1; }
EIP=$(host_field "$EXP" multica public)
# ALTER DATABASE 只对新连接生效：重启 backend 让连接池重连，读回设置，并确认镜像里的 migration 564 已应用（输出形如 on|t）
$(exp_ssh "$EXP") ubuntu@"$EIP" "cd /opt/multica && sudo docker compose exec -T postgres psql -U multica -d multica -v ON_ERROR_STOP=1 -c \"ALTER DATABASE multica SET multica.wakeup_self_refire = '$VALUE'\" \
  && sudo docker compose restart backend >/dev/null \
  && curl -fsS --max-time 20 --retry 6 --retry-delay 5 --retry-all-errors http://127.0.0.1:8080/healthz >/dev/null \
  && sudo docker compose exec -T postgres psql -U multica -d multica -Atc \"SELECT current_setting('multica.wakeup_self_refire', true), EXISTS (SELECT 1 FROM schema_migrations WHERE version = '564_swh13_wakeup_self_refire')\""
