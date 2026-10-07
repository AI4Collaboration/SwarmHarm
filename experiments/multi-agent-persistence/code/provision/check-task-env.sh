#!/bin/bash
# 在 runtime 实例上以 root 运行：把 /tmp/gold.patch 与 /tmp/test.patch 应用到临时 worktree，运行 F2P 测试文件，然后删除 worktree 与两个补丁。
# 参数：REPO_NAME TEST_FILE [F2P_TEST_ID]；调用方先把两个补丁 scp 到 runtime 的 /tmp。
set -euo pipefail
REPO_NAME=$1; TEST_FILE=$2; F2P=${3:-}
cleanup() {
  sudo -u agent -H bash -c "cd ~/work/$REPO_NAME && git worktree remove --force /tmp/check 2>/dev/null; git worktree prune"
  rm -f /tmp/gold.patch /tmp/test.patch
  rm -rf /tmp/check
}
trap cleanup EXIT
chmod 644 /tmp/gold.patch /tmp/test.patch
sudo -u agent -H env REPO_NAME="$REPO_NAME" TEST_FILE="$TEST_FILE" F2P="$F2P" bash <<'EOC'
set -euo pipefail
cd ~/work/$REPO_NAME
source .venv/bin/activate
git worktree add -q --detach /tmp/check work
cd /tmp/check
git apply /tmp/gold.patch
git apply /tmp/test.patch
git status --short
python - <<'PY'
import importlib
m = importlib.import_module(__import__("os").environ["REPO_NAME"])
print("module under test:", m.__file__)
PY
if [ -n "$F2P" ]; then
  echo "== F2P test"
  python -m pytest -q "$F2P" 2>&1 | tail -n 5
fi
echo "== test file"
python -m pytest -q "$TEST_FILE" 2>&1 | tail -n 5
EOC
