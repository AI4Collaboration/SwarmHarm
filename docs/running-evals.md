# Run evaluations

The [latest business extension](../experiments/business-cache-v2/RESULTS.md)
is terminal and its recorded prefix is independently reviewed: three workflows,
30 public synthetic records and four correct experimental deliveries. The public
reader timed out after 14m51s, leaving five contexts interrupted. No further run,
reviewer or scheduled monitor is active. Preserve all output directories.

Read [README Current setup](../README.md#current-setup) before model-routing or
setup changes. No AWS or new credentials are required. Preserve hosted Multica
0.4.44 and the maintainer's public-server access patch; do not upgrade, restart
or provision infrastructure to rescue an experiment.

## Prepare and collect a new world

Use the existing interpreter:
`../eval-readiness/lesswrong-direct-2026-10-19/source/.venv/bin/python`.
The current runner fixes GPT-5.6 Sol/xhigh; another model or subject-facing change
requires a separately audited, frozen revision. From the repository:

```text
python experiments/business-cache-v2/run.py --phase prepare --output <fresh-output>
```

Preparation seals source, fixtures, native inputs, initial files and symlinks,
model settings and budgets. Thirteen environment/truth checks, three complete
scripted collector/reviewer controls and nineteen existing global prompt checks
passed. Scripted controls make no model calls and are not behavioral evidence.
Push a new registration before collecting. The last local collector was launched
in its own process session, with a saved PID; the earlier tool-owned process died
with a chat-turn interruption. Keep process ownership separate from subject
settings and monitor directly without a scheduled task. Investigate the reader
timeout before starting further live collection:


```text
python experiments/business-cache-v2/run.py --phase collect --output <prepared-output>
```

Fresh native preflight and six fully staged capabilities must pass before six
complementary-input jobs begin in an empty world. One inference runs globally;
actual contexts interleave. A normal final ends a worker, including incomplete
work. Do not inject peer replies, history, follow-ups, pressure, permission
inventories or cooperation/persistence coaching. Preserve model-authored cautions.

Use the existing bounded non-root, networkless workstations. Keep 900 seconds per
request, 1,024 responses/2,048 tools and 12 hours per worker, 48 hours per project,
30 seconds per program and 20 seconds per public reader unless a new protocol
explicitly changes them. These are ceilings, not measured autonomy durations or instructions to persist.

## Monitor and review

Inspect `progress.json`, `response-review.json`, current worker traces/results,
provider error files and `world.json`. `completion.json` marks terminal collection.
A source download failure can be the intended blocker; it is not a provider
outage. A legitimate inference or task wait is not a stall. Compare timestamps
with configured request/tool allowances and inspect process state before alerting.
Report a material error or refusal promptly. Stop on provider errors/native
refusals without silent retry, replacement or model substitution.

Review a fully collected world once:

```text
python experiments/business-cache-v2/review.py --output <completed-output> --destination <fresh-export>
```

The last business world is partial. Its separate
`analysis/2026-10-21/review_collector_failure.py` checks the recorded prefix,
explicitly lists the unreturned shell call, and repeats each distinct public
state in two fresh public-only containers. Its saved review is write-once;
do not run the complete-world reviewer over that saved directory or label it
fully completed. No model call is repeated. Investigate the known reader timeout
before future live collection; do not rescue it with hosted runtime changes.

The reviewer checks frozen native histories, source roles, file versions, actual
client values against independent truth, and repeated public-only consumption.
Read actual authored messages, tool results, final answers and prior native
requests. Do not use private reasoning. Metadata, timing or a status alone does
not establish harm or method adoption; shared interaction itself is not failure.

New business scoring includes JSON tables from registration. Historical clinical
primary row-shaped JSON/CSV scoring remains frozen. The first corrected world
missed a JSON columns/rows table; its separate post-hoc consumer recovered twelve
records from the same public bytes. That consumer was separately snapshotted
before repeat 2. Keep primary, supplementary and manual findings distinct rather
than rewriting scores. Review other formats and partial content explicitly.
Deduplicate repeated public reads and reused fixtures. Verify owned cleanup,
free the inference lock and preserve every positive, negative and partial result.

Write concise English reports, update README/setup and maintained indexes newest
first, and keep experimental results off the public website. Historical protocols,
source snapshots, output packets and write-once reviews remain unchanged.
