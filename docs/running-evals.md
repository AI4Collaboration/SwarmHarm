# Run and debug evaluations

SwarmHarm uses one continuous registered rollout. Phase 1 and Phase 2 have
separate gates, but there is no standalone Phase 2 runner and no trajectory
stitching.

## Runtime

- Harbor 0.24.0 at `../eval-readiness/harbor-0.24.0`;
- AxonHub Responses endpoint `https://lmportal.iefbr14.xyz/v1/responses`;
- selected Sol and upstream route `openai/gpt-6.1-sol`;
- reasoning effort `high`, 300-second request timeout, three transport
  attempts and 16,384 output tokens per response;
- 60 minutes per agent across both phases and 75 minutes per rollout;
- four concurrent provider requests for the canonical four-agent rollout; and
- a host-only AxonHub key file outside the repository.

Catalog verification does not pin a provider channel. Apply the current
user-selected channel scope before collection; any fallback must remain within
it and keep the same model. Record actual executions and routing changes during
collection. See [routing](axonhub-routing.md).

No AWS resource is required for the current local study.

## Offline validation

```sh
PY=../eval-readiness/harbor-0.24.0/bin/python
$PY -m unittest discover -s experiments/swarmharm-v1 -p '*checks.py' -v
$PY experiments/prompt-contract/checks.py
./scripts/check-format-contract experiments/swarmharm-v1
python3 scripts/check_dataset_admission_contract.py
```

These checks make no model calls. They validate task truth, the Phase 1 gate,
the Phase 1→Phase 2 continuity contract, native action ordering and independent domain outcomes, prompt surfaces, Harbor inputs
and ATIF export logic. Passing them does not constitute behavioral evidence.

## Prepare one rollout

Finish code and documentation first. Then create a fresh output and a fresh
registration. Check [working context](working-context.md) for an active collector
before starting anything.

```sh
OUT=../eval-readiness/swarmharm-v1-<fresh-run-id>
REG=experiments/swarmharm-v1/registrations/<fresh-run-id>

$PY experiments/swarmharm-v1/run.py \
  --phase prepare --scenario engineering-capacity \
  --output "$OUT" --registration-dir "$REG" \
  --key-file <host-only-key-file> \
  --model-id openai/gpt-6.1-sol --model-alias sol \
  --population 4 --active-contexts 4 --provider-concurrency 4 \
  --filing-deadline-utc <shared-future-ISO-8601-timestamp> \
  --cue-condition agent_initiated_activity
```

Preparation verifies the exact upstream and AxonHub route, writes Harbor 1.4
packages, freezes the Phase 1 and Phase 2 plans, runs offline controls and seals
all source and input hashes, including the frozen protocol. The maintained
study defaults to the exact Sol
route for preparation and collection. A future model must be selected
explicitly and frozen in its own registration.

The four public scenario choices are `engineering-capacity`, `data-analysis`,
`financial-analysis` and `knowledge-work`. Release and maintenance modules are
internal shared dependencies and offline fixtures, not alternate launch targets.

Knowledge Work supports `--scenario knowledge-work` with
`--information-condition local_records` or `staffing_register`. Each model and
condition needs its own fresh output and registration. Keep one common deadline
and all other settings fixed. Never treat the condition as an awareness label.

Both `OUT` and the key file must remain outside the repository. Inspect the
assembled inputs, commit and push the registration, make sure the worktree is
clean, then edit no frozen file. Any source change requires a new registration.

## Collect

Automatic status uses developer-role platform records; task assignments use the
user role. Native requests and ATIF retain this distinction. Notification timing
and unchanged-state suppression are independent of source identity.

Collection refuses to start unless the worktree is clean and local `HEAD`,
remote `main`, the committed registration, the prepared copy and every sealed
source/input hash match.

```sh
$PY experiments/swarmharm-v1/launch.py \
  --output "$OUT" --registration-dir "$REG" \
  --key-file <host-only-key-file>
```

The existing two preflight calls validate the actual Phase 1 and Phase 2 tool
schemas before any subject starts. They execute only the service check, never a
subject business operation, and do not enter subject histories.

The launcher confirms `started.json` before returning success. Do not update
progress documents until that acknowledgment. An early startup failure is
preserved without replacing its output; prepare a new registration.

Current Phase 1 uses subject-created source requests, with no automatic case
opening, private-record matching or generated sharing instructions. The current
activity view provides chronological pagination and case filtering, with all
authored bytes preserved and explicit next offsets. Stronger
cue conditions must be explicitly registered and cannot support an unprompted
discovery claim.

One controller runs both phases. It releases the full Phase 1 population through
one start barrier. Engineering also schedules one final-build publication at
90 seconds from that start, independently of agent communication. It supersedes
compatibility evidence while preserving the existing lookup routes and receipt
history. Idle contexts receive a build-service update when it occurs.
Knowledge Work likewise schedules one copy-desk source revision at 90 seconds,
retaining old statements and reopening only affected source reviews. Its
business handover waits for the current reviews. Both schedules are independent
of communication and require no acknowledgement.

Knowledge Work also applies one registered supplier rota amendment 45 seconds
after the continuation assignment. It changes actual opening bookings, preserves
issued history and authored drafts, and leaves cancelled or reduced bookings
alone. Pending supplier work keeps idle contexts available without inference;
only its real state change produces a status notice. Model calls and event
chronology remain in real time. The amendment is independent of agent actions.

In the current scenario, incomplete work can receive one state-aware reminder after
one second for business state that changed after its latest request. Facts
already delivered do not trigger another call, even after a first blocked final. Peer notes and other jobs'
progress do not renew it. New cases and their initial notes produce ordinary
notifications; later entries notify agents that have already posted in that
case. This changes delivery only: every otherwise eligible agent can still read
all records. No hidden private-record matching selects recipients.

Passive notices name changed cases or customer-visible activity without repeating
the assignment. Knowledge Work Phase 1 also reports actual new event types and
counts (case, note, follow-up or attachment), without authored content or source
locators. Delivery is not an exact read. Old release activity does not wake Phase 2. A completed assignment
remains available without timed nags; cancellations and blocked outcomes stay intact.
Operator milestones never enter the prompt. Automatic statuses use developer
provenance; human assignments use user provenance. Each selected model receives
one registration and collector; never collect a completed registration again.

After the first Phase 1 pass and the scenario's business handover, the controller
drains in-flight requests and assigns ordinary Phase 2 work to the same live
contexts, without a fixed observation wait. Separately authorized model rollouts
may run independently in parallel. Request
timestamps measure real elapsed time; workload schedules use virtual minutes. It does not reset histories, workstations, shared state or event
IDs. In `engineering-capacity`, ordinary booking checks the customer's included capacity;
plan import uses a genuine quote's recorded availability. A booking schedules
execution in the future customer window. Cancellation and rescheduling remain
available. Independent replay executes the final commitments with fixed pool
capacity, including each actor alone and leave-one-out comparisons. Phase 2
needs no extra dialogue round trip. Each customer credential reads only
its customer pool, account and booking; another customer's booking does not create
a private notification. Agent-authored operations entries remain shared. Provider
background schedules remain outside subject control for independent replay.
A separate durable work queue checks actual completion at the deadline; no
checkpoint failure is converted into data disappearance. Unreserved
work incurs the registered customer delay credit in replay; report that baseline
cost separately from additional system loss. Keep scope and actual model
identity in every report.

Monitor `progress.json`, `natural/phase1-progress.json` and its append-only
`.jsonl` history, `controller.log`, response classifications, transport
attempts and actor traces. Preserve failures; never silently restart or replace
a trajectory. There is no response-count or tool-call-count cap. The registered
actor and rollout wall-clock bounds terminate the intact rollout rather than
continuing with a smaller population.

Terminal cleanup records the end time of every remaining context after in-flight
requests drain. A local request timeout clipped by the rollout or actor deadline
is recorded as a budget timeout, retaining the original error. HTTP, model-identity
and ordinary full-duration transport failures remain separate provider failures.
Runtime changes need a fresh registration; never retroactively modify earlier scores.

## Reproduce a published example

The current examples name their source commit and registration commit in
[the result index](research/current-rollout-result.json). Use that frozen revision
and its archived source to review or reproduce an example. Current launch-menu
cleanup and later documentation do not retroactively change its registration.
Do not collect into a completed output or reseal its files; a new model rollout
always needs fresh registration and output directories.

## Review and export

After `completion.json` exists:

```sh
$PY experiments/swarmharm-v1/review.py --output "$OUT"
$PY experiments/swarmharm-v1/export_atif.py "$OUT"
```

The collector first writes `evidence-manifest.json`, which binds the completed
raw evidence. Review verifies that manifest and reconciles the mutable world
snapshot against append-only per-tool commits before deriving any result. The
independent review reports Phase 1 and Phase 2 separately. The overall
rollout passes only if Phase 1 passes first, continuity holds, and the complete
Phase 2 outcome checks are satisfied. Each ATIF trajectory contains
one agent's continuous history across both phases.

For an offline Phase 1 measurement audit of the canonical agent-initiated
condition, use a new report file outside the frozen output:

```sh
$PY experiments/swarmharm-v1/review.py --output "$OUT" \
  --reassess-phase1 /absolute/path/to/a-new-audit.json
```

This checks the evidence manifest and native delivery, writes a separate
interpretation, and never rewrites the frozen score or invents Phase 2 execution.
It makes no model calls. A repaired live evaluator still needs fresh registration
and collection when the user authorizes them.

Keep raw outputs outside Git. Public case excerpts require explicit user
authorization and must stay separate from technical prompts and pass criteria.
