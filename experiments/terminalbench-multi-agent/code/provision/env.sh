# SWH-30 共享配置。所有脚本 source 本文件；每个实验的状态放在 .scratch/<EXP>/ 下
export AWS_PROFILE=eurosafeai AWS_DEFAULT_REGION=eu-central-1
VPC=vpc-0dc6260011176dcae
SUBNET=subnet-0f9b3bc5da2c0c635
AMI=ami-0b8a830d6339a9758          # Ubuntu 24.04 LTS amd64, eu-central-1
SVC_TYPE=t3.small                  # multica 与 proxy 实例
ADMIN_CIDR=195.176.112.0/24
RUNTIME_CIDR=10.76.1.0/24          # runtime 所在子网（proxy 的 squid 只服务这个网段）
AXONHUB_HOST=lmportal.iefbr14.xyz
AXONHUB_URL=https://$AXONHUB_HOST
META_HOST=63.186.173.73            # SWH-6 AxonHub host (AxonHub admin API on 127.0.0.1:8090)
BUCKET=swarmharm-swh13-artifacts-906513713427
MULTICA_IMAGE_KEY=images/multica-backend-v0.6.1-swh13.tar.gz
MULTICA_TAG=v0.6.1
ACME_EMAIL=swarmharm@tac.ch
ADMIN_EMAIL=admin@tac.ch           # Multica 用户名由邮箱前缀得到：admin
ISSUE_TAG=SWH-44
BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATH="$BUNDLE_DIR/.scratch/bin:$PATH"

# 所有 EC2 共用同一把 SSH 密钥。私钥保存在 S3（swh30/ssh/），首次使用时下载到 .scratch/ssh/
SHARED_KEY_NAME=swh30-shared
SHARED_KEY="$BUNDLE_DIR/.scratch/ssh/swh30-shared-ed25519"
fetch_shared_key() {
  if [ ! -f "$SHARED_KEY" ]; then
    mkdir -p "$(dirname "$SHARED_KEY")"
    aws s3 cp --quiet "s3://$BUCKET/swh30/ssh/swh30-shared-ed25519" "$SHARED_KEY"
    aws s3 cp --quiet "s3://$BUCKET/swh30/ssh/swh30-shared-ed25519.pub" "$SHARED_KEY.pub"
    chmod 600 "$SHARED_KEY"
  fi
}

# 读取 experiments.json 中某实验的字段。用法：exp_field TB01 n_agents
exp_field() { python3 -c "import json,sys; print(json.load(open('$BUNDLE_DIR/experiments.json'))[sys.argv[1]][sys.argv[2]])" "$1" "$2"; }
# 读取 tasks.json 中某任务的字段。用法：task_field takens-embedding-lean instance_type
task_field() { python3 -c "import json,sys; print(json.load(open('$BUNDLE_DIR/tasks.json'))[sys.argv[1]][sys.argv[2]])" "$1" "$2"; }
# 实验目录与 SSH 封装
exp_dir() { echo "$BUNDLE_DIR/.scratch/$1"; }
exp_ssh() { echo "ssh -i $SHARED_KEY -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -o ServerAliveInterval=15"; }
# infra.json 中按角色名取字段。用法：host_field TB01 rt-a public
host_field() { python3 -c "import json,sys; print([h for h in json.load(open('$BUNDLE_DIR/.scratch/$1/infra.json')) if h['name']=='swh30-$1-'+sys.argv[1]][0][sys.argv[2]])" "$2" "$3"; }
# 字母序号：1->a 2->b ...
letter() { printf "\\$(printf '%03o' $((96 + $1)))"; }
