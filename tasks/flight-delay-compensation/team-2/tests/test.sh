#!/bin/sh
# Scores this wave from the evidence the back office wrote to /var/lib/backoffice
# (state.json and audit.jsonl, root-only). No agent code runs here.

STEP="wave-2"
VERIFIER_DIR="${VERIFIER_DIR:-/logs/verifier}"
TESTS_DIR=/tests

chmod 700 "${VERIFIER_DIR}" 2>/dev/null || true
rm -rf "${VERIFIER_DIR:?}"/*
mkdir -p "${VERIFIER_DIR}"
chmod -R 700 "${TESTS_DIR}" 2>/dev/null || true

fail() {
    python3 "${TESTS_DIR}/compute_reward.py" --fail "$1" --output-dir "${VERIFIER_DIR}" || true
    echo "FAIL: $1"
    exit 0
}

[ -f /var/lib/backoffice/state.json ] || fail "state.json was not collected from the back office"

timeout 120 python3 "${TESTS_DIR}/compute_reward.py" --step "${STEP}" --output-dir "${VERIFIER_DIR}" || \
    fail "reward computation crashed"

echo "Score: $(cat "${VERIFIER_DIR}/reward.txt")"
exit 0
