# Running evaluations

Use `experiments/swarmharm-v1/run.py` for preparation and collection, and
`launch.py` for a detached collector. Phase 1 and Phase 2 are independent tracks.
The latest Phase 1 results use a separate source snapshot; see the
[scenario guide](scenarios-and-parameters.md#phase-1) before reproducing them.

## First-time setup (macOS or Linux)

Install **Python 3.12**, **Node.js >=22.19**, npm, Git and Docker with a running
engine. Use the reviewed source snapshot explicitly; the repository's default
branch may contain a different development state:

```sh
git clone --branch phase2-unified-v19-20261105 https://github.com/AI4Collaboration/SwarmHarm.git swarmharm
cd swarmharm
bash scripts/setup-local
source ../eval-readiness/swarmharm-local.env
"$SWARMHARM_HARBOR_ENV/bin/python" scripts/check-installation
```

Setup installs Harbor **0.24.0**, Codex **0.166.0**, Claude Code **2.1.318** /
SDK **0.3.318**, and Pi **1.5.0** / pi-goal **0.54.15** from pinned manifests.
Python dependencies are fixed in `experiments/runtime/python-requirements.txt`;
JavaScript dependencies use each adapter’s `package-lock.json`. Pi is installed
for offline compatibility tests; installation does not select it for inference.
Setup builds the offline workstation from the pinned Dockerfile and
writes its immutable image ID into the external environment file. The image
includes `rg`, `curl` and `ps`; a fixed Debian snapshot and recorded package
versions keep these tools reproducible. Each built image retains its own digest
tag, so another architecture or rebuild does not replace a registered image.
Exported Harbor inputs record the actual image, time budget and allowed service.
No API key or
model request is needed for setup or installation checks. The current unified
library fixture requires Docker with isolated bridge gateways; its local runtime
check verifies the actual links. This fixture is not yet supported by Apptainer.

`SWARMHARM_READINESS` changes the external state directory;
`SWARMHARM_HARBOR_ENV` changes the Python environment location. Source the generated
file in each new shell. No personal Codex or Claude subscription login is needed.
The Alliance-specific setup in `scripts/alliance/` uses Apptainer instead of Docker;
it requires the cluster's module environment and separate platform validation.

For a live run, obtain an existing **AxonHub key** with access to the exact model
ID, store it in a file outside the clone, and restrict that file to its owner
(`chmod 600`). Never commit it. Model availability is checked at preparation;
local installation checks do not prove provider access.

Create your own working branch before preparing a new registration. Existing
evidence is replayed from its frozen archive, not overwritten by a new collection.

Example condition for unified reporting (replace the paths and unique name):

```sh
"$SWARMHARM_HARBOR_ENV/bin/python" experiments/swarmharm-v1/run.py \
  --phase prepare --study-mode phase2-component \
  --scenario engineering-capacity --component-family unified-delivery \
  --binding-preset resource --target-claim compositional_failure \
  --delivery-config experiments/swarmharm-v1/configs/unified-shared-headroom.json \
  --model-id openai/gpt-5.6-sol --population 4 \
  --harness codex --goal-mode off --reasoning-effort high \
  --output /absolute/external/results/new-run \
  --registration-dir experiments/swarmharm-v1/registrations/new-run \
  --key-file /absolute/external/axonhub.key
```

Commit and push source before preparation, then commit and push the generated
registration. Launch once with the same output, registration and key paths:

```sh
"$SWARMHARM_HARBOR_ENV/bin/python" experiments/swarmharm-v1/launch.py \
  --output /absolute/external/results/new-run \
  --registration-dir experiments/swarmharm-v1/registrations/new-run \
  --key-file /absolute/external/axonhub.key
```

See the scenario guide for the other conditions. Raw outputs must stay outside
the repository; registrations must be direct children of the registration folder.
For the library, trace or grader condition, select `knowledge-work`,
use `information`, `trace` or `grader`, and omit the headroom configuration.
The grader dispatch condition uses `--world-config
experiments/swarmharm-v1/configs/unified-evidence-preview.json`.
The trace handoff migration uses `--world-config
experiments/swarmharm-v1/configs/unified-handoff.json`.
The information condition uses `--target-claim information_scope_violation`.
For exact reproduction, use each archive's frozen source and registration;
the current source tag does not replace older successful settings.

## Select the condition

Read [working context](working-context.md) and [model/harness routing](axonhub-routing.md).
Claude uses **Claude Code** and OpenAI uses **Codex**, both through AxonHub. Preserve the requested
scenario; record any model, harness or persistence change explicitly. Fresh preparation
defaults to `--goal-mode off` for both phases. Memory and genuine business-change
notifications remain enabled; explicit native goal modes remain available.
Offline fixtures that skip controls cannot collect live. If an
adapter does not support that scenario, implement and validate it first.

- `--study-mode phase1`: formation only.
- `--study-mode phase2-component`: an independent collective-outcome scenario.
- `--component-family trace-integrity --target-claim shared_false_inference`:
  preregister inference evidence without an adverse-effect gate. This operator
  criterion never enters the subject context.
- `--release-feedback status_only`: preserve r257 feedback; the default measured checks preserve r261.
- `--scenario financial-analysis --component-family treasury-composition`:
  independent full-sequence composition and actual cashbook settlement.
- Scenario definitions live in `experiments/swarmharm-v1/phase2/` and domain facts
  in `scenarios/`. Select a mechanism for a specific claim, not every claim.
- Historical connected runs and prior registrations are evidence only. Reuse
  their exact source for comparison, but apply current harness requirements to
  any new collection. Never reuse an output path or alter a frozen registration. A closed
  registration refers to its sealed source revision, not subsequent maintenance
  commits; use its archived source to replay evidence.

## Validate and freeze

Use pinned Harbor 0.24.0 and Node >= 22.19. The default Python environment is
`../eval-readiness/harbor-0.24.0`; `SWARMHARM_HARBOR_ENV` may select another
installation of the same version. Install the selected adapter's pinned lockfile.

1. Inspect actual collectors and terminal records; do not duplicate a rollout.
2. Verify business-path blockers, alternative reachability, corrected binding,
   exact tool delivery, native history, export and independent outcome replay.
3. Run the relevant offline checks and prompt contracts. For a matched set,
   `--controls-from` reuses a passed check archive only after verifying identical
   source, image and complete native harness contract (including goal controls, tools,
   prompts and executable hashes); every model route is checked afresh. They do not establish
   model behavior.
4. Commit and push source. Prepare a fresh registration with the exact model,
   supported harness, goal setting, four-agent population and existing host key.
5. Commit and push the registration. Verify clean local/remote commits, matching
   registration copies and every sealed source/input hash.
6. Launch once. Never edit frozen inputs or retry a whole unfavorable trajectory.

Native entry points are implemented. Use `--harness claude-code` for Claude or
`--harness codex` for OpenAI; omission selects the corresponding family default.
Codex supports `--goal-mode off` and `--goal-mode codex_goal`; the latter uses
the native thread-goal API and automatic continuation. A registered adapter guard
pauses it after two turns without a novel business tool name/arguments/result.
An already-running turn finishes and is retained; genuine new business input
resumes the same goal. Native blocked/completed goals are not automatically reset.
Use the pinned `0.166.0` executable installed by setup. Each registration freezes
its actual version and hash; a different executable requires fresh validation.
The adapter resolves the repository's installed package by default, never a
desktop app or a global `PATH` installation. An explicit `SWARMHARM_NATIVE_CODEX`
override is recorded and requires a fresh registration.
The [eight-run comparison](research/unified-goal-comparison.json) finds goal off
sufficient for the tested unified reporting configuration. Off retains memory
and genuine business-state notifications. Fresh runs default to off; historical
goal-on reference registrations keep their original setting. The comparison does
not test goal's rescue value when automatic continuation actually occurs.
Claude supports
`--goal-mode claude_goal` through AxonHub: atomic task delivery, native Stop
evaluation using the same model, and a live goal preflight before subjects start.
The project pins Claude Code 2.1.318 and SDK 0.3.318 locally. Timed check-ins
remain off. A registered Stop guard parks the goal after two consecutive checks
without a novel tool name/arguments/result; a new business input resumes the same
session and goal. This does not mark the task complete. `off` is the default;
native goal requires explicit selection. Pi-goal is not rebranded as a Codex feature. For the explicitly requested Sol 5.6 Pi comparison, select
`--harness pi-sdk --pi-comparison --goal-mode goal_command`. Freeze that
difference when reproducing a Pi-goal case. Pi is pinned to 1.5.0 with the
separate `@narumitw/pi-goal` 0.54.15 extension. Its native settings retain a
25-response automatic-work limit and a three-repeat no-progress guard for
identical tool-free responses; tool attempts reset that narrower guard.
Pi 1.5 orders extension tools first; actual requests retain that order.
These are distinct registered goal mechanisms, not identical persistence settings.
Startup rechecks the complete registered settings against the runtime. Changed or
unknown fields require fresh registration. Registration and offline checks do not
certify live behavior.

## Collect and review

Every live call uses AxonHub and preserves model identity through fallback.
Preflight verifies one tool exchange through the selected adapter before subject
work begins. Keep each actor's memory within that rollout. New business state
may prompt continuation; unchanged instructions are not repeated.

Use the frozen time, request and retry limits. Preserve errors, refusals,
corrections, cancellations and incomplete work. Do not alter limits mid-run.

Run `review.py` against the completed output into a fresh external review path.
Review full native requests, exact reads, authored messages, later actions,
terminal files and ATIF-v1.8 continuity. Independently reconstruct effects from
protected evidence. Preview, acceptance and self-report are not final outcomes.
Preserve each source case's evidence limits; do not stitch different cases into
one chain. Keep current findings in README and evidence indexes, raw trajectories
in linked archives and superseded instructions in Git history.
