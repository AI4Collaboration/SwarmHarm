# SWH-13 共享配置。所有脚本 source 本文件；每个实验的状态放在 .scratch/<EXP>/ 下
export AWS_PROFILE=eurosafeai AWS_DEFAULT_REGION=eu-central-1
VPC=vpc-0dc6260011176dcae
SUBNET=subnet-0f9b3bc5da2c0c635
AMI=ami-0b8a830d6339a9758          # Ubuntu 24.04 LTS amd64, eu-central-1
TYPE=t3.small
ADMIN_CIDR=195.176.112.0/24
AXONHUB_HOST=lmportal.iefbr14.xyz
AXONHUB_URL=https://$AXONHUB_HOST
META_HOST=63.186.173.73            # SWH-6 AxonHub host (AxonHub admin API on 127.0.0.1:8090)
BUCKET=swarmharm-swh13-artifacts-906513713427
MULTICA_IMAGE_KEY=images/multica-backend-v0.6.1-swh13.tar.gz
MULTICA_TAG=v0.6.1
ACME_EMAIL=swarmharm@tac.ch
ADMIN_EMAIL=admin@tac.ch           # Multica 用户名由邮箱前缀得到：admin
BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATH="$BUNDLE_DIR/.scratch/bin:$PATH"

# 读取 experiments.json 中某实验的字段。用法：exp_field E01 n_agents
exp_field() { python3 -c "import json,sys; print(json.load(open('$BUNDLE_DIR/experiments.json'))[sys.argv[1]][sys.argv[2]])" "$1" "$2"; }
# 实验目录与 SSH 封装
exp_dir() { echo "$BUNDLE_DIR/.scratch/$1"; }
exp_ssh() { echo "ssh -i $BUNDLE_DIR/.scratch/$1/swh13-$1-ed25519 -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -o ServerAliveInterval=15"; }
# infra.json 中按角色名取字段。用法：host_field E01 rt-a public
host_field() { python3 -c "import json,sys; print([h for h in json.load(open('$BUNDLE_DIR/.scratch/$1/infra.json')) if h['name']=='swh13-$1-'+sys.argv[1]][0][sys.argv[2]])" "$2" "$3"; }
# 字母序号：1->a 2->b ...
letter() { printf "\\$(printf '%03o' $((96 + $1)))"; }
