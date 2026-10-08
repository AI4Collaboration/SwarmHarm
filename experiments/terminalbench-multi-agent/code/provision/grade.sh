#!/bin/bash
# 在本机 docker 里用 Terminal-Bench 官方 verifier 给一个交付物打分。参数：TASK ARTIFACT_TAR OUT_DIR
# ARTIFACT_TAR 是以任务的 artifact_root 为根目录打的 tar.gz（final.tar.gz 或 collect.sh 从 runtime 取回的同格式文件）。
# 流程：构建（或复用）tests/Dockerfile 镜像 -> 创建容器 -> 把交付物复制到 artifact_root -> 运行 /tests/test.sh -> 读取 reward.txt
set -euo pipefail
source "$(dirname "$0")/env.sh"
TASK=$1
ARTIFACT=$(cd "$(dirname "$2")" && pwd)/$(basename "$2")
mkdir -p "$3"; OUT=$(cd "$3" && pwd)
TD="$BUNDLE_DIR/tasks/$TASK"
ROOT=$(task_field "$TASK" artifact_root)
IMAGE=swh30-verifier-$TASK
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  docker build -q -t "$IMAGE" "$TD/tests" > "$OUT/verifier-image-build.log"
fi
rm -rf "$OUT/artifact" "$OUT/logs"; mkdir -p "$OUT/artifact" "$OUT/logs"
tar xzf "$ARTIFACT" -C "$OUT/artifact"
CID=$(docker create -v "$OUT/logs:/logs/verifier" --entrypoint bash "$IMAGE" /tests/test.sh)
trap 'docker rm -f "$CID" >/dev/null 2>&1 || true' EXIT
docker cp "$OUT/artifact/." "$CID:$ROOT/"
START=$(date +%s)
set +e
docker start -a "$CID" > "$OUT/verifier-stdout.log" 2>&1
RC=$?
set -e
END=$(date +%s)
REWARD=$(cat "$OUT/logs/reward.txt" 2>/dev/null || echo missing)
python3 - "$OUT" "$TASK" "$REWARD" "$RC" "$((END - START))" <<'PY'
import json, sys
out, task, reward, rc, seconds = sys.argv[1:6]
result = {"task": task, "reward": reward, "resolved": reward.strip() == "1", "verifier_exit_code": int(rc), "seconds": int(seconds)}
try:
    ctrf = json.load(open(f"{out}/logs/ctrf.json"))
    result["tests"] = ctrf["results"]["summary"]
except FileNotFoundError:
    result["tests"] = None
json.dump(result, open(f"{out}/result.json", "w"), indent=1)
print(json.dumps(result))
PY
