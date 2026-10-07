#!/bin/bash
# 在 runtime 实例上以 root 运行（网络仍开放时）：把 SWE-Bench Pro 任务仓库放到 agent 用户目录并装好测试环境。
# 参数：TASK（T1-ansible-combine-vars | T2-qutebrowser-search-url）。调用方先把 tasks/<TASK>/ 目录 scp 到 /opt/swh13/task/。
# 环境全部以 agent 用户身份创建，这样 uv 管理的 Python 和 venv 都属于 agent。
set -euo pipefail
TASK=$1
TD=/opt/swh13/task
case "$TASK" in
  T1-ansible-combine-vars)
    ACTIVATE_EXTRA='export PYTEST_ADDOPTS="-p no:cacheprovider"'
    SMOKE="test/units/utils/test_vars.py test/units/vars/test_variable_manager.py" ;;
  T2-qutebrowser-search-url)
    ACTIVATE_EXTRA='export PYTEST_QT_API=pyqt5
export QUTE_QT_WRAPPER=PyQt5
export QT_QPA_PLATFORM=offscreen
export PYTEST_ADDOPTS="-p no:cacheprovider -W ignore::pytest.PytestRemovedIn8Warning"'
    SMOKE="tests/unit/utils/test_urlutils.py" ;;
  *) echo "unknown task $TASK"; exit 1 ;;
esac
# runtime 上只放 env.json 与 requirements.lock（没有 gold/test patch 和测试名单）
if ! { test -f "$TD/env.json" && test -f "$TD/requirements.lock" && ! test -e "$TD/gold.patch" && ! test -e "$TD/test.patch" && ! test -e "$TD/meta.json"; }; then
  echo "task dir must contain only env.json and requirements.lock"; exit 1
fi
sudo -u agent -H env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u NO_PROXY -u no_proxy TD="$TD" ACTIVATE_EXTRA="$ACTIVATE_EXTRA" SMOKE="$SMOKE" bash <<'EOC'
set -euo pipefail
REPO=$(python3 -c "import json;print(json.load(open('$TD/env.json'))['repo'])")
BASE=$(python3 -c "import json;print(json.load(open('$TD/env.json'))['base_commit'])")
NAME=${REPO##*/}
WORK=$HOME/work/$NAME
mkdir -p "$HOME/work"
if [ ! -d "$WORK/.git" ]; then
  git clone -q "https://github.com/$REPO.git" "$WORK"
fi
cd "$WORK"
git checkout -q "$BASE"
git clean -fdxq -e .venv
# 让 agent 看到的是一个普通的开发者本地仓库：没有 origin 远端，base commit 上有一个工作分支
git remote remove origin 2>/dev/null || true
git branch -f work "$BASE" && git checkout -q work
git config user.name "agent" && git config user.email "agent@localhost"
# 删除 base commit 之后的全部历史：其他分支、标签、reflog，并清除不可达对象，避免 agent 从仓库对象库里读到上游的修复提交
for b in $(git for-each-ref --format='%(refname)' refs/heads refs/remotes refs/tags | grep -v '^refs/heads/work$'); do git update-ref -d "$b"; done
git reflog expire --expire=now --all
git gc -q --prune=now
if [ "$(git rev-list --all --count)" != "$(git rev-list work --count)" ]; then echo "repository still has commits outside the work branch"; exit 1; fi
if [ "$(git count-objects -v | awk '/^garbage/ {print $2}')" != 0 ]; then echo "object store has garbage"; exit 1; fi
if [ ! -x .venv/bin/python ]; then
  uv python install 3.11 >/dev/null 2>&1
  uv venv -q --python 3.11 .venv
  uv pip install -q --compile-bytecode --python .venv/bin/python -r "$TD/requirements.lock"
  uv pip install -q --compile-bytecode --python .venv/bin/python --no-deps -e .
  printf '%s\n' "$ACTIVATE_EXTRA" >> .venv/bin/activate
fi
# 冒烟：在未打任何补丁的 base commit 上跑相关测试文件，证明环境可用
source .venv/bin/activate
python --version
python -m pytest -q $SMOKE 2>&1 | tail -3
git status --short | head -5; git log --oneline -1
EOC
