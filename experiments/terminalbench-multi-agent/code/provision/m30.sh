#!/bin/bash
# 以干净环境调用 multica 0.6.1 CLI，指向某个实验的自建 Multica。用法：m30.sh EXP <multica args...>
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
EXP=$1; shift
ACCOUNT="$DIR/.scratch/$EXP/multica-account.json"
EIP=$(python3 -c "import json; print([h for h in json.load(open('$DIR/.scratch/$EXP/infra.json')) if h['name']=='swh30-$EXP-multica'][0]['public'])")
cd "$HOME"
exec env -i HOME="$HOME" PATH="$DIR/.scratch/bin:/usr/local/bin:/usr/bin:/bin" \
  MULTICA_SERVER_URL="https://$EIP" \
  MULTICA_WORKSPACE_ID="$(jq -r .workspace.id "$ACCOUNT")" \
  MULTICA_TOKEN="$(jq -r .pat "$ACCOUNT")" \
  multica --profile "swh30-$EXP" "$@"
