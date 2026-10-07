#!/bin/bash
# 在 runtime 实例上以 root 运行：在一次性 worktree 里应用 gold.patch 与 test.patch，运行 F2P 测试文件，随后清理。
# 参数：TEST_FILE。调用方先把两个 patch 放到 /tmp/swh13-check/（脚本结束时删除）。
set -euo pipefail
TEST_FILE=$1
CK=/tmp/swh13-check
NAME=$(python3 -c "import json;print(json.load(open('/opt/swh13/task/env.json'))['repo'].split('/')[-1])")
REPO=/home/agent/work/$NAME
test -f $CK/gold.patch && test -f $CK/test.patch
chmod 755 $CK; chmod 644 $CK/*.patch
cleanup() {
  sudo -u agent -H env REPO=$REPO bash -c 'cd $REPO && git worktree remove --force ../swh13-check-wt 2>/dev/null; git worktree prune; git branch -D swh13-check 2>/dev/null' || true
  rm -rf $CK
}
trap cleanup EXIT
sudo -u agent -H env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy CK=$CK REPO=$REPO TEST_FILE="$TEST_FILE" bash <<'EOC'
set -euo pipefail
cd $REPO
git worktree add -q -b swh13-check ../swh13-check-wt work
cd ../swh13-check-wt
git apply --index $CK/gold.patch
git apply --index $CK/test.patch
git diff --cached --stat | tail -n 5
# 复用主工作区的 venv：从 worktree 目录运行，PYTHONPATH 指向 worktree 内的源码
source $REPO/.venv/bin/activate
export PYTHONPATH=$PWD/lib:$PWD
python -c "import ansible; print(ansible.__file__)" 2>/dev/null || true
python -m pytest -q $TEST_FILE 2>&1 | tail -n 5
EOC
echo "cleanup follows"
