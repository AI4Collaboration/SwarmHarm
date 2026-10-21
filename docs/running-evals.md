# Run evaluations

The [latest v3 world completed](../experiments/business-cache-v3/analysis/2026-10-21/COMPLETE_REPORT.md):
six correct normal reports, six correct experimental reports and thirty original
synthetic rows publicly recovered. All 206 responses accepted; no provider,
authentication or reader fault/refusal. Independent review and actual cleanup
passed. No collector, reviewer, scheduled monitor or next run is active. Keep the
prior overload/login interruptions distinct. The completed world discloses remote
push confirmation overlapping preflight despite earlier local input/source freeze.

The [public-reader repair](../experiments/infra-reader-v1/REPORT.md) passed 53
model-free controls and 1,320 stress observations. Business v3 has also passed
the completed live study. The
[earlier business v2 result](../experiments/business-cache-v2/RESULTS.md) remains
partial: 30 public synthetic records and four correct deliveries before the old
reader timeout. No reviewer or scheduled monitor is active. Preserve
all historical output directories.

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
python experiments/business-cache-v3/run.py --phase prepare --output <fresh-output>
```

Preparation seals source/dependencies, fixtures, native inputs, initial files and
symlinks, reader configuration, model settings and budgets. V3 passed twelve
reader, thirteen business-truth, eight whole-flow, one launcher and nineteen
existing global prompt controls. Its twelve initial native input/file sets exactly
match frozen v2. These controls make no model calls and are not behavioral evidence.
Push the new registration before collection. Use the launcher to separate process
ownership from the chat turn; it verifies the seal, records the PID, rejects
duplicate launch and starts an independent process session:

```text
python experiments/business-cache-v3/launch.py --output <prepared-output>
```

Fresh native preflight and six fully staged capabilities must pass before six
complementary-input jobs begin in an empty world. One inference runs globally;
actual contexts interleave. A normal final ends a worker, including incomplete
work. Do not inject peer replies, history, follow-ups, pressure, permission
inventories or cooperation/persistence coaching. Preserve model-authored cautions.

Use the existing bounded non-root, networkless workstations. Keep 900 seconds per
request, 1,024 responses/2,048 tools and 12 hours per worker, 48 hours per project,
30 seconds per subject program. The registered v3 reader has separate limits:
60 seconds for creation, 30 for attachment, 10 for in-container execution and
15 per control/cleanup command. It allows at most two reader-only attempts for
retryable lifecycle faults and reuses checksummed receipts only for identical
public bytes/image/decoder/wrapper/execution bound. Every event records fresh or
cached provenance. These are ceilings, not measured autonomy durations or
instructions to persist. Model calls are never retried to rescue a trajectory.

## Monitor and review

Inspect `launcher.json` and its PID, `controller.log`, `progress.json`,
`response-review.json`, current worker traces/results, provider errors and
`world.json` directly, without a scheduled task. Each phase also saves
`operator/tool-commits`, `operator/observations` and
`operator/public-reader/lifecycle.jsonl`. Business results/public snapshots commit
before observation. A persistent observer failure saves the regular trace/native
output pair and `observer-hold.json`, marks pending measurement, and stops before
dispatching any later tool call. Do not treat it as zero exposure, provider failure
or permission to resume/replace a trajectory. `completion.json` marks terminal collection.
A source download failure can be the intended blocker; it is not a provider
outage. A legitimate inference or task wait is not a stall. Compare timestamps
with configured request/tool allowances and inspect process state before alerting.
A generic `provider_error` may originate before network dispatch: inspect the
actual exception and saved request/response files. Local auth-file absence is
not an upstream response or refusal; use the existing login and never commit
credentials or replay an interrupted world. Report a material error or refusal promptly. Stop on provider errors/native
refusals without silent retry, replacement or model substitution.

Review a fully collected world once:

```text
python experiments/business-cache-v3/review.py --output <terminal-output> --destination <fresh-export>
```

For v3, the reviewer verifies durable commits and receipt provenance and repeats
each distinct public state twice with fresh readers. It separately lists pending
measurements and undispatched native tool calls. A passed history audit with
`measurement_complete: false` does not mean the eval completed or exposure is zero.

The historical v2 world is partial. Its separate
`analysis/2026-10-21/review_collector_failure.py` checks the recorded prefix,
explicitly lists the unreturned shell call, and repeats each distinct public
state in two fresh public-only containers. Its saved review is write-once;
do not run the complete-world reviewer over that saved directory or label it
fully completed. The repair changes observation timing in a separate revision;
it does not complete this old world or authorize historical model calls to repeat.

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
