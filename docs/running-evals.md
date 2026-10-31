# Running evaluations

Every rollout uses the common registered harness pipeline in
`experiments/swarmharm-v1/run.py`. Phase-specific environments live in `phase1/`
and `phase2/`; harness adapters live in `experiments/runtime/`. No separate
custom direct-API loop is maintained. The current Knowledge Work comparison uses `evidence`, `method_available`,
`accepted_packet` and native Pi goal, following the compiled-packet baseline. Reproducing the frozen Engineering
reference examples requires their original source and registration.

## Choose scope and harness

- `--study-mode phase1`: autonomous discovery and live formation only. No Phase 2
  assignment or tools are exposed, and review makes no Phase 2 claim.
- `--study-mode connected`: Phase 1 first, then the same sessions, workstations,
  histories and shared state continue into Phase 2. In-flight work finishes before
  tool activation; the registered source handover must also be ready.
- `--study-mode phase2-component --scenario engineering-capacity --component-family terminal-records-server`:
  recover each released layout and deliver the replay. Docker exposes one isolated
  archive link per owner. The four links and journal are saved for independent review.
- `--study-mode phase2-component --scenario engineering-capacity --component-family terminal-batching`:
  external reservation service; use `business_records_only`. Empty
  discussion tools and immutable intake are supplied, with no prepared method.
- `--study-mode phase2-component --scenario engineering-capacity --component-family terminal-acceptance`:
  internal comparison forecast, four workload owners and the original approved budget.
- `--study-mode phase2-component --scenario knowledge-work`: start with declared
  business inputs. Select `--component-family external-service|acceptance|evidence`
  and `--initial-material business_records_only|need_available|method_available`.
  This evaluates neither formation nor end-to-end continuity.
  For `evidence`, `--proof-stage compiled_packet|accepted_packet` registers the
  optional print-production service. The default `off` preserves the earlier task.

All modes accept the same `--harness` selection:

- **`pi-sdk` (default):** Pi 1.4.0 and its registered prompt, with contextual
  work instructions appended. The initial business request remains user input.
  Use AxonHub and the existing host-only key; Sol 6.1 is the development baseline,
  and Sol 5.6 is authorized for current component work.
- **`claude-code`:** Claude Agent SDK 0.3.312 and Claude Code >= 2.1.304 with an
  explicitly selected native model. Uses subscription auth and the stock Claude
  Code preset. Declared work context is ordinary user input, not a native
  developer-role message.
- **`codex`:** Codex CLI 0.141.0 app-server, an explicitly selected native model
  and ChatGPT subscription auth. The stock instructions remain unchanged; work
  context is ordinary user input. The same private thread survives tool reload.

Registering a harness records its installed version, native prompt/preset,
context mapping, tools, effort, goal setting, retry behavior and source hashes.
These differences are experimental conditions. An adapter being available is
not authorization to change the chosen model or live route.

Independent components provide empty public/private discussion tools. Private
messages are absent from the manager review feed; both channels are fully research
logged. All live messages must be authored by the evaluated agents. Prepared
artifacts are recorded as supplied material. `--material-distribution
one_workstation` supplies method files only to fixture index 0 and requires
`method_available`; ordinary source access remains unchanged.

The component's default `--goal-mode off` uses a private work plan. It can resume
a subject-authored unfinished step once; waiting stays incomplete. Independent
components also support native Pi `--goal-mode goal_command` as a separately
registered condition, with private-plan tools and reminders removed. Pi-goal
0.54.13 contributes its own instructions and explicit 25 automatic-turn / three
no-progress-turn limits. Its no-progress measure is repeated tool-free text,
not business progress. Active goals and timed waits remain live until native
termination or the registered time limit; goal status never proves completion.
Claude `--goal-mode claude_goal` is available for other study modes, not components.
Use `scripts/check_goal_mode_pair.py` before claiming a matched goal comparison;
it preserves exact business prompts, tools, materials, source and deadline.

## Install and validate locally

Use the pinned Harbor 0.24.0 Python and Node >= 22.19. The default Python environment is `../eval-readiness/harbor-0.24.0`. Set
`SWARMHARM_HARBOR_ENV` to use a different environment directory; the launcher,
Harbor wrapper and format checker all honor it and still require Harbor 0.24.0.
Install the selected adapter from its lockfile:

```sh
npm ci --prefix experiments/runtime/pi
# Only when testing or selecting the Claude adapter:
npm ci --prefix experiments/runtime/claude
```

Subscription adapters require their own installed CLI and existing subscription
login. `SWARMHARM_CLAUDE` and `SWARMHARM_CODEX` may point to dedicated pinned
binaries; do not replace a user's global installation. Claude requires
`claude auth login`; Codex requires `codex login`. Never pass an API key or
custom endpoint to either subscription adapter. Native model IDs must be found
in the authenticated catalog; do not substitute an unrequested model.

Workstations use the pinned Docker image; inspect `experiments/runtime/workstation.py`
for its immutable default. `scripts/build-workstation-image` and
`scripts/alliance/` support explicitly configured build/cluster setups. A changed
image or backend is a fresh registered condition, not reproduction of the old one.

To check all adapters, install their pinned dependencies and point the CLI
variables to the matching binaries, then run from the repository root:

```sh
EVAL_PY="${SWARMHARM_HARBOR_ENV:-../eval-readiness/harbor-0.24.0}/bin/python"
$EVAL_PY -B -m unittest discover -s experiments/swarmharm-v1/tests -p '*checks.py' -t experiments/swarmharm-v1
$EVAL_PY -B experiments/prompt-contract/checks.py
./scripts/check-format-contract experiments/swarmharm-v1
$EVAL_PY scripts/check_dataset_admission_contract.py
```

Native adapter checks use local scripted provider endpoints, not hosted model
inference. They test delivery, ordering, continuation and export; they do not
show model behavior. Preparation runs the common contracts and the selected
adapter's native checks, so unused adapters need not be installed.

## Prepare a fresh rollout

Finish source and documentation edits, commit and push them first. Set a fresh
output path outside Git, a fresh registration name and the existing host-only
AxonHub key path. Example for the current independent component:

```sh
EVAL_PY="${SWARMHARM_HARBOR_ENV:-../eval-readiness/harbor-0.24.0}/bin/python"
$EVAL_PY experiments/swarmharm-v1/run.py --phase prepare \
  --output "$ROLLOUT_OUTPUT" --registration-dir "$ROLLOUT_REGISTRATION" \
  --harness pi-sdk --goal-mode goal_command --key-file "$AXONHUB_KEY_FILE" \
  --model-id openai/gpt-5.6-sol --model-alias sol56 --reasoning-effort high \
  --population 4 --study-mode phase2-component --scenario knowledge-work \
  --component-family evidence --initial-material method_available \
  --proof-stage accepted_packet --material-distribution all_workstations
```

All four workstations start with business records, the explicitly declared
saved-import rehearsal, native goals and empty discussion channels. Validation
availability and proof files are intermediate observations; final customer
records are independently materialized and checked against the immutable ledger.

For the Phase 1 baseline, use `--study-mode phase1 --scenario knowledge-work`,
`--model-id openai/gpt-6.1-sol`, and omit component-specific options. For a connected
study use `--study-mode connected`. These select scope, not independent launchers.
Keep the current `agent_initiated_activity` cue default unless a new condition
is explicitly intended.

Preparation verifies the selected route, runs offline controls and freezes
source, tasks, inputs, private files, tools, budget and harness metadata. Commit
and push the registration next. Do not edit frozen source or inputs afterward.
Before inference, the collector verifies a clean tree, committed registration
bytes, source/input/task hashes and local/remote HEAD equality. A named branch
must match its `origin` branch; detached HEAD must match `origin/main`.

Default Pi routing is AxonHub's native same-model fallback, preferring eligible
non-OpenRouter channels. Do not constrain the key to the old two-channel profile.
Catalog checks prove availability, not the actual channel. Record execution
provenance where exposed; see [routing](axonhub-routing.md). Historical direct
OpenRouter registrations retain their original endpoint and require their
original frozen code to reproduce. They are not the current launch default.

## Collect and inspect

```sh
$EVAL_PY experiments/swarmharm-v1/launch.py \
  --output "$ROLLOUT_OUTPUT" --registration-dir "$ROLLOUT_REGISTRATION" \
  --key-file "$AXONHUB_KEY_FILE"
```

Subscription launches omit the key file. Launch reads the frozen harness rather
than accepting a new one. A per-output lock and existing-start check prevent
replacement collectors. Preflight performs one service/tool round trip through
that harness before subjects start; it does not execute scenario work.

All contexts cross one start barrier. Private shell execution overlaps while
shared state commits remain ordered. Each native tool receives its committed
result. Four agents, 60 minutes per actor and 75 minutes per rollout remain the
default; virtual business schedules do not change real request chronology.
The selected harness's frozen retry and token-limit metadata is authoritative.

The controller does not repeat unchanged tasks. The pinned native Pi goal still
issues its own automatic continuation prompts; record their usefulness separately.
Actual business revisions may wake a
settled context; passive notes do not reset its reminder allowance. Private plan
continuations refer only to an actor-authored distinct next step. Phase 2 outcome
checks require no extra dialogue round trip. Budgets, quiescence and goal status
must not be relabeled as business completion.

Inspect `progress.json`, `natural/phase1-progress.json`, `natural/actors.json`,
`controller.log`, native traces and the terminal `completion.json`. Milestones are
operator-only. Provider errors/filters, interrupted collection, incomplete work,
accepted records and independently executed outcomes are separate facts.

## Review and export

```sh
$EVAL_PY experiments/swarmharm-v1/export_atif.py "$ROLLOUT_OUTPUT"
$EVAL_PY experiments/swarmharm-v1/review.py --output "$ROLLOUT_OUTPUT" \
  --destination "$ROLLOUT_REVIEW"
```

Use a fresh external review destination. The terminal manifest binds collected
bytes. Review checks the frozen evaluator, committed tools, actual messages and
reads, complete action sequences, corrections/cancellations and independent
final effects. ATIF-v1.8 validates with Harbor 0.24.0. A preview, accepted import
or claimed completion is not final outcome evidence.

Pi records the adapter's request/response payloads and session history. Claude
records the SDK message stream and session files; Codex records app-server
messages and native thread/session evidence. Their controller projections are
not provider HTTP captures. Unexposed internal prompts, auxiliary calls or token
limits must not be invented. Export reconciles native echoes and result order,
including rejected calls and interrupted delivery.

## Frozen examples

The [Sol Phase 1 baseline](research/phase1-baseline.json) is v98/r136 at source
`3dfff613`, registration `99bde55d`. It had four live read-back threads; its
continuation ended safely incomplete. The [connected positives](research/current-rollout-result.json)
and [component positive](research/phase2-component-positive.json) retain separate
claims. Aman’s [Pi Finance result](research/current-finance-pi-sol-result.json)
uses its original OpenRouter route.

To replay historical evidence, check out its exact source and registration in a
separate directory and use that revision's commands. Current path moves do not
rewrite its hashes. Never relaunch into the original output, stitch trajectories
or use an older success to certify this new runtime.

For a historical matched goal comparison after repairing the comparison tool,
`check_goal_mode_pair.py --allow-verifier-update FIRST SECOND` permits only that
operator checker and its component test to differ, and reports their hashes.
Runtime, environment, outcome evaluator and subject inputs remain exact. Fixture
contents are compared after actor-ID normalization; their original truth digest
must first bind the recorded payload. Do not use this option for an environment
or harness change.

The current evidence condition also indexes a replacement field-validation booking.
The work order and source index link the service appointment. It is scheduled after
the delivery date; its completion reference is empty. Time alone generates no result,
approval, notification or goal resumption. The task, retained-snapshot behavior,
rendering rehearsal and outcome standard stay fixed.
