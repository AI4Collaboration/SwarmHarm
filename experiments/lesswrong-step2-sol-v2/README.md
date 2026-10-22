# LessWrong Step 2 reproduction on GPT-5.6 Sol v2

This version keeps the public Step 2 task, both worlds, GPT-5.6 Sol settings,
100-turn budget and 64 trials per condition unchanged. It changes only provider
failure handling after v1 stopped on two incomplete AxonHub streams.

The public LessWrong launcher preserved separate attempt directories and retried
an incomplete eight-sample shard up to ten times. This local runner instead
retries only the failed provider request, at most nine times after its initial
attempt. It retries HTTP 408, 429 and selected 5xx responses, provider stream
errors, and streams that end without a terminal response. Every failed request
remains in the evidence directory. It never reruns a sample or trajectory.

This narrower retry keeps the agent's existing context and avoids replacing
completed model actions. AxonHub still replaces the paper's OpenRouter route,
GPT-5.6 Sol replaces Claude Opus 4.8 as judge, and local Docker replaces Daytona.
These differences must remain visible in the report.

Only `completion.json` establishes 128 completed trials. Communication is the
only measured outcome; it is not evidence of misalignment or harm.

## Run

```sh
PY=../eval-readiness/lesswrong-direct-2026-10-19/source/.venv/bin/python
OUT=../eval-readiness/lesswrong-step2-sol56-<date>-r2
PARENT=../eval-readiness/lesswrong-direct-2026-10-19

$PY experiments/lesswrong-step2-sol-v2/run.py --phase prepare \
  --output "$OUT" --pinned-parent "$PARENT"
$PY experiments/lesswrong-step2-sol-v2/run.py --phase preflight \
  --output "$OUT" --pinned-parent "$PARENT" --key-file <host-only-key-file>
$PY experiments/lesswrong-step2-sol-v2/run.py --phase collect \
  --output "$OUT" --pinned-parent "$PARENT" --key-file <host-only-key-file>
$PY experiments/lesswrong-step2-sol-v2/review.py --output "$OUT"
```
