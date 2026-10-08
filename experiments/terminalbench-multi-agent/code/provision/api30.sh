#!/bin/bash
# 直接调用实验 Multica 的 REST API（admin PAT）。用法：api30.sh EXP METHOD PATH [JSON_BODY]
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
EXP=$1; METHOD=$2; P=$3; BODY=${4:-}
ACCOUNT="$DIR/.scratch/$EXP/multica-account.json"
EIP=$(python3 -c "import json; print([h for h in json.load(open('$DIR/.scratch/$EXP/infra.json')) if h['name']=='swh30-$EXP-multica'][0]['public'])")
args=(-fsS -X "$METHOD" "https://$EIP$P" -H "Authorization: Bearer $(jq -r .pat "$ACCOUNT")" -H "X-Workspace-ID: $(jq -r .workspace.id "$ACCOUNT")" -H 'Content-Type: application/json')
if [ -n "$BODY" ]; then args+=(-d "$BODY"); fi
curl "${args[@]}"
