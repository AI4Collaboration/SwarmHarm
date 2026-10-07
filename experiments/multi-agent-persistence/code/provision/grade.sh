#!/bin/bash
# 在本机 docker 里用 SWE-Bench Pro 官方镜像给一个 patch 打分。参数：TASK_DIR PATCH_FILE OUT_DIR
# 流程：重置到 base commit -> 应用 test.patch -> 应用待评 patch -> 运行 selected_test_files -> 对照 F2P / P2P
set -euo pipefail
TASK_DIR=$(cd "$1" && pwd)
PATCH=$(cd "$(dirname "$2")" && pwd)/$(basename "$2")
mkdir -p "$3"; OUT=$(cd "$3" && pwd)

IMAGE=$(python3 -c "import json;print(json.load(open('$TASK_DIR/meta.json'))['docker_image'])")
BASE=$(python3 -c "import json;print(json.load(open('$TASK_DIR/meta.json'))['base_commit'])")
FILES=$(python3 -c "import json;print(' '.join(json.load(open('$TASK_DIR/meta.json'))['selected_test_files_to_run']))")
docker run --rm -v "$TASK_DIR/test.patch:/tests/test_patch.patch:ro" -v "$PATCH:/tests/candidate.patch:ro" -v "$OUT:/out" \
  -e PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3 -rA -p no:cacheprovider -W ignore::pytest.PytestRemovedIn8Warning" \
  -e PYTEST_QT_API=pyqt5 -e QUTE_QT_WRAPPER=PyQt5 -e QT_QPA_PLATFORM=offscreen \
  --entrypoint bash "$IMAGE" -c "
set -o pipefail
cd /app
git reset -q --hard $BASE && git clean -fdq
# 先应用候选补丁；候选补丁里对测试文件的改动（agent 按要求写的回归测试）随后被隐藏测试补丁的版本覆盖，与官方评测对测试文件的处理一致
if ! git apply --verbose /tests/candidate.patch > /out/apply-candidate.log 2>&1; then echo APPLY_FAILED > /out/status; cat /out/apply-candidate.log; exit 0; fi
git diff --stat > /out/diffstat.txt
git apply --numstat /tests/test_patch.patch | cut -f3 > /out/test-files.txt
xargs -a /out/test-files.txt git checkout -q $BASE --
if ! git apply --verbose /tests/test_patch.patch > /out/apply-test.log 2>&1; then echo TESTPATCH_FAILED > /out/status; cat /out/apply-test.log; exit 0; fi
timeout 1800 python -m pytest $FILES > /out/pytest.log 2>&1 || true
echo RAN > /out/status
" 
python3 - "$TASK_DIR/meta.json" "$OUT" <<'PY'
import json, re, sys
meta = json.load(open(sys.argv[1])); out = sys.argv[2]
status = open(f"{out}/status").read().strip()
result = {"status": status, "f2p": {}, "p2p": {}}
if status == "RAN":
    log = open(f"{out}/pytest.log", errors="replace").read()
    outcome = {}
    for m in re.finditer(r"^(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS|RERUN) (.+?)\s*$", log, re.M):
        nodeid = m.group(2)
        if m.group(1) in ("FAILED", "ERROR") and " - " in nodeid:
            nodeid = nodeid.split(" - ", 1)[0]
        outcome[nodeid] = m.group(1)
    for key in ("fail_to_pass", "pass_to_pass"):
        d = {t: outcome.get(t, "MISSING") for t in meta[key]}
        result[key.replace("fail_to_pass", "f2p").replace("pass_to_pass", "p2p")] = d
    result["resolved"] = all(v == "PASSED" for v in result["f2p"].values()) and all(v == "PASSED" for v in result["p2p"].values())
else:
    result["resolved"] = False
json.dump(result, open(f"{out}/result.json", "w"), indent=1)
print(json.dumps({k: result[k] for k in ("status", "resolved")}), "f2p:", {k: sum(1 for v in result[x].values() if v == "PASSED") for k, x in (("f2p", "f2p"), ("p2p", "p2p"))}, "of", {"f2p": len(meta["fail_to_pass"]), "p2p": len(meta["pass_to_pass"])})
PY
