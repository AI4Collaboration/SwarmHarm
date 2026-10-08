#!/bin/bash
# 在 runtime 实例上以 root 运行：安装共享 SSH 密钥，使同一实验内的 runtime 之间可以互相登录。
# 参数：SELF_NAME PEER... ，PEER 形如 dev-b=10.76.1.23（含自身以外的全部 runtime）。
# 调用方先把共享私钥与公钥 scp 到本机 /home/ubuntu/swh30-key{,.pub}（本脚本使用后删除）。
set -euo pipefail
SELF=$1; shift
KEY_SRC=/home/ubuntu/swh30-key
test -f $KEY_SRC && test -f $KEY_SRC.pub
hostnamectl set-hostname "$SELF"
sed -i "s/^127.0.1.1.*//" /etc/hosts
grep -q "127.0.1.1 $SELF" /etc/hosts || echo "127.0.1.1 $SELF" >> /etc/hosts
for peer in "$@"; do
  name=${peer%%=*}; ip=${peer#*=}
  grep -q " $name\$" /etc/hosts || echo "$ip $name" >> /etc/hosts
done
for user in agent ubuntu; do
  home=$(getent passwd $user | cut -d: -f6)
  install -d -m 700 -o $user -g $user $home/.ssh
  install -m 600 -o $user -g $user $KEY_SRC $home/.ssh/id_ed25519
  install -m 644 -o $user -g $user $KEY_SRC.pub $home/.ssh/id_ed25519.pub
  touch $home/.ssh/authorized_keys
  grep -qF "$(cat $KEY_SRC.pub)" $home/.ssh/authorized_keys || cat $KEY_SRC.pub >> $home/.ssh/authorized_keys
  chown $user:$user $home/.ssh/authorized_keys; chmod 600 $home/.ssh/authorized_keys
  cat > $home/.ssh/config <<EOC
Host dev-*
    User agent
    IdentityFile ~/.ssh/id_ed25519
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    LogLevel ERROR
EOC
  chown $user:$user $home/.ssh/config; chmod 600 $home/.ssh/config
done
rm -f $KEY_SRC $KEY_SRC.pub
