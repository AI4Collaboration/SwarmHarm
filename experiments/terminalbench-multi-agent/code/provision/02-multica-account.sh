#!/bin/bash
# 在本机运行：在实验的 Multica 上创建 admin 用户、长期 PAT 和 workspace。参数：EXP
set -euo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1; D=$(exp_dir "$EXP")
EIP=$(host_field "$EXP" multica public)
SSH="$(exp_ssh "$EXP") ubuntu@$EIP"
API="https://$EIP"
OUT="$D/multica-account.json"
if [ -f "$OUT" ] && jq -e .pat "$OUT" >/dev/null 2>&1; then echo "account already created"; jq '{user:.me.name,workspace_id:.workspace.id}' "$OUT"; exit 0; fi
curl -fsS -X POST "$API/auth/send-code" -H 'Content-Type: application/json' -d "{\"email\":\"$ADMIN_EMAIL\"}" >/dev/null
sleep 3
CODE=$($SSH 'sudo docker compose --project-directory /opt/multica logs backend --since 3m 2>/dev/null' | grep -oE 'Verification code for [^:]+: [0-9]{6}' | tail -1 | awk '{print $NF}')
[ -n "$CODE" ]
JWT=$(curl -fsS -X POST "$API/auth/verify-code" -H 'Content-Type: application/json' -d "{\"email\":\"$ADMIN_EMAIL\",\"code\":\"$CODE\"}" | jq -r .token)
[ -n "$JWT" ] && [ "$JWT" != null ]
# 用户名必须是 admin：邮箱前缀已经是 admin，再显式写一次保证一致
curl -fsS -X PATCH "$API/api/me" -H "Authorization: Bearer $JWT" -H 'Content-Type: application/json' -d '{"name":"admin"}' >/dev/null
PAT=$(curl -fsS -X POST "$API/api/tokens" -H "Authorization: Bearer $JWT" -H 'Content-Type: application/json' -d "{\"name\":\"swh30-$EXP-operator\",\"expires_in_days\":0}" | jq -r .token)
[ -n "$PAT" ] && [ "$PAT" != null ]
ME=$(curl -fsS "$API/api/me" -H "Authorization: Bearer $PAT")
WS=$(curl -fsS -X POST "$API/api/workspaces" -H "Authorization: Bearer $PAT" -H 'Content-Type: application/json' -d "{\"name\":\"Dev Workspace\",\"slug\":\"dev\",\"issue_prefix\":\"DEV\"}")
jq -n --arg pat "$PAT" --argjson me "$ME" --argjson ws "$WS" '{pat:$pat, me:$me, workspace:$ws}' > "$OUT"
chmod 600 "$OUT"
jq '{user: .me.name, email: .me.email, user_id: .me.id, workspace_id: .workspace.id, slug: .workspace.slug}' "$OUT"
