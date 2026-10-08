#!/bin/bash
# 在 runtime 实例上以 root 运行：把任务的参考解法放进一次性副本里运行，证明这台机器上的任务环境和性能满足任务要求，随后清理。
# 参数：TASK。调用方先把 tasks/<TASK>/solution/ 的内容 scp 到 /tmp/swh30-check/solution/（脚本结束时删除）。
# 任务目录（/task、/app）本身不被改动。
set -euo pipefail
TASK=$1
CK=/tmp/swh30-check
test -d $CK/solution
chmod -R a+rwX $CK
cleanup() { rm -rf $CK /tmp/chk-task /tmp/chk-app; }
trap cleanup EXIT
case "$TASK" in
  takens-embedding-lean)
    # 与 verifier 相同的做法：新建项目副本，.lake/packages 指向 /task 里的 Mathlib，叠加参考证明后编译并审计公理
    sudo -u agent -H env ELAN_HOME=/opt/elan PATH=/opt/elan/bin:$PATH bash <<'EOC'
set -euo pipefail
mkdir -p /tmp/chk-task/.lake && cd /tmp/chk-task
cp /task/lakefile.toml /task/lean-toolchain /task/lake-manifest.json /task/GSLean.lean .
cp -r /task/GSLean .
ln -s /task/.lake/packages .lake/packages
cp -r /tmp/swh30-check/solution/lean_files/GSLean/Takens/. GSLean/Takens/
time lake build GSLean 2>&1 | tail -n 5
printf 'import GSLean\n#print axioms takens_embedding_existential\n' > _axioms.lean
lake env lean _axioms.lean
EOC
    ;;
  data-anonymization)
    sudo -u agent -H bash <<'EOC'
set -euo pipefail
cd /tmp/swh30-check
time python3 solution/anon.py /app/input --policy /app/policy.yaml --output /tmp/swh30-check/out --seed 42 --max-memory 64MB
for f in /app/input/*.csv; do
  b=$(basename $f)
  echo "$b input_rows=$(wc -l < $f) output_rows=$(wc -l < /tmp/swh30-check/out/$b)"
done
EOC
    ;;
  batched-eval-parity)
    sudo -u agent -H bash <<'EOC'
set -euo pipefail
mkdir -p /tmp/chk-app && cp -r /app/evalbench /app/model /app/data /tmp/chk-app/
cp /tmp/swh30-check/solution/*.py /tmp/chk-app/evalbench/
cd /tmp/chk-app
echo "== public_runtime, packed, batch 64 (verifier limit: 55 s)"
time python evalbench/evaluate.py --data data/public_runtime.jsonl --batch-size 64 --padding-side left --batch-mode packed --model-dir /tmp/chk-app/model --cache-dir /tmp/chk-app/cache --out /tmp/chk-app/runtime.json
echo "== public_eval, packed, batch 8"
time python evalbench/evaluate.py --data data/public_eval.jsonl --batch-size 8 --padding-side left --batch-mode packed --model-dir /tmp/chk-app/model --cache-dir /tmp/chk-app/cache2 --out /tmp/chk-app/eval.json
python -c "import json; d=json.load(open('/tmp/chk-app/eval.json')); print(d['metrics']['total'], d['metrics']['overall_accuracy'])"
EOC
    ;;
  *) echo "unknown task $TASK"; exit 1 ;;
esac
echo "task check done: $TASK"
