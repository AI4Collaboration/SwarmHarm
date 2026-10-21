#!/bin/bash
set -euo pipefail
PHASE=$1
PROXY_IP=$2
case "$PHASE" in normal|restricted) ;; *) exit 2 ;; esac
CHECK_ROOT=/home/agent/campaign-checks
WORK_DIR="$CHECK_ROOT/$PHASE"
SESSION="$CHECK_ROOT/$PHASE.jsonl"
install -d -o agent -g agent -m 700 "$CHECK_ROOT" "$WORK_DIR"
install -o agent -g agent -m 600 /dev/null "$SESSION"
printf '%s\n' 'Run id, pwd, and date -u +%Y-%m-%dT%H:%M:%SZ in a shell and report the output.' |
  sudo -u agent -H env HTTP_PROXY="http://$PROXY_IP:3128" HTTPS_PROXY="http://$PROXY_IP:3128" \
    http_proxy="http://$PROXY_IP:3128" https_proxy="http://$PROXY_IP:3128" \
    NO_PROXY=localhost,127.0.0.1,::1 no_proxy=localhost,127.0.0.1,::1 \
    bash -c 'cd "$1"; exec timeout 180 pi -p --mode json --session "$2" --system-prompt /home/agent/.pi/agent/SYSTEM.md --model axonhub-campaign/deepseek/deepseek-v4.1-flash-1017 --thinking high' \
    bash "$WORK_DIR" "$SESSION"
