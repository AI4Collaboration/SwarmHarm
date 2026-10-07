#!/bin/bash
# 在本机运行：从 meta host 的 AxonHub 列出实验窗口内各 agent key 的请求元数据，从 S3 下载请求/响应体，
# 与 collect.sh 的导出一起打成 swh13-<EXP>-traces.tar.xz。参数：EXP META_SSH_KEY
set -euo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1; META_KEY=$2; D=$(exp_dir "$EXP"); OUT="$D/export"; N=$(exp_field "$EXP" n_agents)
SINCE=$(cat "$D/started-at.txt")
KEYS=""; for i in $(seq 1 "$N"); do KEYS="$KEYS swh13-$EXP-rt-$(letter $i)"; done
MSSH="ssh -i $META_KEY -o StrictHostKeyChecking=accept-new ubuntu@$META_HOST"
scp -q -i "$META_KEY" "$BUNDLE_DIR/provision/axonhub-list-requests.py" ubuntu@$META_HOST:/tmp/swh13-list.py
$MSSH "sudo python3 /tmp/swh13-list.py $SINCE $KEYS" > "$OUT/axonhub-requests-metadata.json"
mkdir -p "$OUT/axonhub/requests"
python3 -c "import json; print('\n'.join(r['id'].split('/')[-1] for r in json.load(open('$OUT/axonhub-requests-metadata.json'))))" > "$D/axonhub-ids.txt"
echo "requests: $(wc -l < "$D/axonhub-ids.txt")"
xargs -a "$D/axonhub-ids.txt" -P 8 -I{} aws s3 cp --recursive --quiet "s3://swarmharm-axonhub-logs-906513713427/1/requests/{}/" "$OUT/axonhub/requests/{}/"
echo "downloaded $(find "$OUT/axonhub/requests" -mindepth 1 -maxdepth 1 -type d | wc -l) request directories, $(find "$OUT/axonhub/requests" -type f | wc -l) files"
# 把导出里的 AxonHub key / Multica token 替换成占位符（包括 agent-home-state.tgz 内部和 AxonHub 请求体），再复查
python3 "$BUNDLE_DIR/provision/redact.py" "$OUT"
if [ "$(python3 "$BUNDLE_DIR/provision/redact.py" "$OUT")" != "redacted: {}" ]; then echo "credential-like strings remain after redaction"; exit 1; fi
cat > "$OUT/README.txt" <<EOC
SWH-13 experiment $EXP trace package
model=$(exp_field "$EXP" model) harness=$(exp_field "$EXP" harness) n_agents=$N task=$(exp_field "$EXP" task)
started_at=$SINCE
multica/          issue, comments, runs, run-messages/<run>.json, wakeups, wakeup-runs/<rule>.json, timeline, attachments/
runtimes/rt-x/    git state and diff against base, daemon journal, agent home state (no venv/repo)
proxy/            squid access log (every proxied request, incl. denied destinations)
axonhub/requests/ AxonHub S3 objects per request id (inbound/upstream request and response bodies, stream chunks)
axonhub-requests-metadata.json  request index with api key name, model, status, timing
grading/          grade.sh results for final.patch and each runtime's working tree
EOC
(cd "$D" && tar cJf "swh13-$EXP-traces.tar.xz" --transform "s,^export,swh13-$EXP," export)
ls -la "$D/swh13-$EXP-traces.tar.xz"
aws s3 cp --quiet "$D/swh13-$EXP-traces.tar.xz" "s3://$BUCKET/traces/swh13-$EXP-traces.tar.xz" && echo "uploaded to s3://$BUCKET/traces/swh13-$EXP-traces.tar.xz"
