#!/bin/bash
# 在 runtime 实例上以 root 运行（网络仍开放时）：按 Terminal-Bench 任务的 environment/Dockerfile 在宿主机上原生搭建任务环境。
# 参数：TASK。调用方先把 tasks/<TASK>/environment/ 目录 scp 到 /opt/swh30/task/environment/。
# 任务路径与容器内一致（/task 或 /app），agent 用户拥有可写权限；隐藏的 tests/ 与 solution/ 不会上传到 runtime。
set -euo pipefail
TASK=$1
TD=/opt/swh30/task/environment
test -d "$TD"
test ! -e /opt/swh30/task/tests && test ! -e /opt/swh30/task/solution
# runtime-base.sh 已经写入指向 proxy 的环境变量，而 proxy 只放行 AxonHub 与 Multica；搭建任务环境时直连互联网
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy NO_PROXY no_proxy
NOPROXY=(env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u NO_PROXY -u no_proxy)
mkdir -p /etc/swh30
: > /etc/swh30/task.env
case "$TASK" in
  takens-embedding-lean)
    # elan 与 Lean 工具链放在 /opt/elan，agent 与 daemon 通过 PATH 前缀使用；Mathlib 缓存来自 lake exe cache get
    export ELAN_HOME=/opt/elan
    mkdir -p /opt/elan /task
    chown agent:agent /opt/elan /task
    echo 'ELAN_HOME=/opt/elan' >> /etc/swh30/task.env
    printf '%s\n' 'export ELAN_HOME=/opt/elan' 'export PATH=/opt/elan/bin:$PATH' > /etc/profile.d/swh30-task.sh
    sudo -u agent -H "${NOPROXY[@]}" ELAN_HOME=/opt/elan bash -c 'curl -sSf https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh | sh -s -- -y --default-toolchain none --no-modify-path'
    install -d -o agent -g agent /task/GSLean
    cp -r "$TD"/lakefile.toml "$TD"/lean-toolchain "$TD"/lake-manifest.json "$TD"/GSLean.lean /task/
    cp -r "$TD"/GSLean/. /task/GSLean/
    chown -R agent:agent /task
    sudo -u agent -H "${NOPROXY[@]}" ELAN_HOME=/opt/elan PATH=/opt/elan/bin:$PATH bash -c 'cd /task && lake exe cache get 2>&1 | tail -n 5; lake build GSLean 2>&1 | tail -n 8; lean --version'
    ;;
  data-anonymization)
    pip3 install --break-system-packages --ignore-installed --quiet PyYAML==6.0.2
    mkdir -p /app /root/data
    cp -r "$TD"/data/. /root/data/
    cp /root/data/policy.yaml /app/policy.yaml
    (cd /app && TB3_SUBJECT_COUNT=120000 TB3_ACCOUNT_COUNT=150000 TB3_ORDER_COUNT=150000 TB3_DEVICE_COUNT=80000 TB3_EVENT_MULTIPLIER=1 python3 /root/data/generate_input.py)
    chmod a-w /app/policy.yaml && chmod -R a-w /app/input
    chown agent:agent /app
    ls -la /app; du -sh /app/input
    ;;
  batched-eval-parity)
    # 镜像是 python:3.11-slim + numpy 1.26.4：用 uv 安装 Python 3.11，python / python3 / pip 通过包装脚本指向该环境
    export UV_PYTHON_INSTALL_DIR=/opt/uv-python
    uv python install 3.11
    uv venv --seed --python 3.11 /opt/py311
    uv pip install --python /opt/py311/bin/python numpy==1.26.4
    for name in python python3 pip; do
      target=/opt/py311/bin/$name
      printf '#!/bin/sh\nexec %s "$@"\n' "$target" > /usr/local/bin/$name
      chmod 755 /usr/local/bin/$name
    done
    mkdir -p /app
    cp -r "$TD"/evalbench "$TD"/model "$TD"/data /app/
    chown -R agent:agent /app
    printf '%s\n' 'PYTHONHASHSEED=0' 'OMP_NUM_THREADS=1' 'OPENBLAS_NUM_THREADS=1' >> /etc/swh30/task.env
    printf '%s\n' 'export PYTHONHASHSEED=0' 'export OMP_NUM_THREADS=1' 'export OPENBLAS_NUM_THREADS=1' > /etc/profile.d/swh30-task.sh
    sudo -u agent -H bash -lc 'python --version; python -c "import numpy; print(numpy.__version__)"'
    ;;
  *) echo "unknown task $TASK"; exit 1 ;;
esac
rm -rf /opt/swh30/task
echo "task environment ready: $TASK"
