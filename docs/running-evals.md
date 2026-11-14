# Running the reporting baseline

For the active three-agent SwarmForm matrix, use the [accepted-input instructions](../README.md#accepted-inputs). The following commands inspect status and preview current development inputs without running tests or models:

```sh
python3 swarmform/scripts/check_swarmform_inputs.py --status
python3 swarmform/scripts/inspect_swarmform_workload.py --staged --dataset-key november --domain "Knowledge Work" --output ../knowledge-preview
```

The preview exports private startup files, separate later deliveries and an operator audit. It uses the development generator; use the default accepted-input exporter for exact reviewed versions. The instructions below run the four-agent reporting baseline, including the reviewed v57 cache pilot.

Use `swarmharm/run.py` for preparation and collection, and
`swarmharm/launch.py` for a detached collector. Unified runs use one continuous task.
Do not combine separate trajectories to represent a unified run.
SwarmHarm's unified rollouts score formation and the registered business consequence
from the same trajectory. SwarmForm can register formation as its primary target,
with no adverse-outcome requirement.

## First-time setup (macOS or Linux)

Install **Python 3.12**, **Node.js >=22.19**, npm, Git and Docker with a running
engine. The default branch contains the maintained unified environment.
Published cases include their exact source in the [evidence bundles](../swarmharm/docs/research/trajectory-release.json).

After a Codex rollout, run `python3 swarmharm/scripts/audit_codex_workstation.py RAW_OUTPUT`
to check delivered inputs for known instrumentation markers. The audit reports
initial files, native instructions, advertised tools, delivered tool results and
agent-authored text with references to the original records. These observations
do not measure private reasoning.

```sh
git clone https://github.com/AI4Collaboration/SwarmHarm.git swarmharm
cd swarmharm
bash scripts/setup-local
source ../eval-readiness/swarmharm-local.env
"$SWARMHARM_HARBOR_ENV/bin/python" scripts/check-installation
```

Setup installs Harbor **0.24.0** and Codex **0.166.0** by default. Add Claude Code
**2.1.318** / SDK **0.3.318** and Pi **1.5.0** / pi-goal **0.54.15** before runs or
checks that use them: `bash scripts/setup-local claude pi` (or `all`). All come from
pinned manifests. Python dependencies are fixed in `shared/python-requirements.txt`;
JavaScript dependencies use each adapter’s `package-lock.json`. Installing a harness
does not select it for inference.
Setup builds the offline workstation from the pinned Dockerfile and
writes its immutable image ID into the external environment file. The image
includes `rg`, `curl`, `ps` and `apply_patch`; a fixed Debian snapshot and recorded package
versions keep these tools reproducible. Each built image retains its own digest
tag, so another architecture or rebuild does not replace a registered image.
The patch command follows the OpenAI Cookbook implementation, with a pinned
source and MIT license in `shared/`. Installation checks exercise
an actual file edit; older images without the command must be rebuilt.
Exported Harbor inputs record the actual image, time budget and allowed service.
No API key or model request is needed for setup or installation checks. The current unified
library fixture requires Docker with isolated bridge gateways; its local runtime
check verifies the actual links. This fixture is not yet supported by Apptainer.

To inspect business inputs before registering or running anything:

```sh
"$SWARMHARM_HARBOR_ENV/bin/python" swarmharm/scripts/inspect_unified_input.py \
  --scenario engineering-capacity --binding-preset control \
  --output ../input-preview
```

The new directory contains normalized parameters and input hashes in `manifest.json`,
tasks, tool definitions, and readable files for all four workstations. Use the same
`--world-config` and `--binding-preset` options as preparation. This checks input
consistency without Docker, credentials or model calls; it does not validate
execution paths or model behavior. Native startup instructions and runtime settings
are sealed separately at registration. An existing export is never overwritten.

### Read the prompts

For one Markdown page per workstation, run the following from the repository root.
The export includes the declared messages, harness prompt configuration, tool
schemas and initial files. The default previews the Knowledge Work records
condition. Supply a registration to read its exact sealed bytes.

```sh
"$SWARMHARM_HARBOR_ENV/bin/python" swarmharm/scripts/dump_prompts.py --output ../current-prompt-preview
"$SWARMHARM_HARBOR_ENV/bin/python" swarmharm/scripts/dump_prompts.py \
  --registration-dir swarmharm/registrations/2026-11-07-unified-v55-formation-records-knowledge-sol61-r1 \
  --output ../sealed-prompt-preview
```

### Check the installation and inputs

Use one entry point for change-selected checks. Previewing the selection does not run tests:

```sh
python3 scripts/check-ci --plan
"$SWARMHARM_HARBOR_ENV/bin/python" scripts/check-ci
```

The default compares with `origin/main`, including local edits. Use `--base COMMIT`
for another comparison. Documentation and progress notes need no Docker or native
harness installation. Operator-witness changes select their small regression checks;
input and runtime changes select the affected contracts and behavior tests. Each
selected check runs once. `--full` explicitly runs the complete offline suite;
`--output ../eval-readiness/checks.json` saves a result. No command here calls a model.

`SWARMHARM_READINESS` changes the external state directory;
`SWARMHARM_HARBOR_ENV` changes the Python environment location. Source the generated
file in each new shell. No personal Codex or Claude subscription login is needed.
The Alliance setup and environment scripts install Apptainer for standalone
workstation checks. The live reporting workflow requires Docker's isolated
workstation-to-library links.

### Registered SwarmForm runtime

The 50 accepted SwarmForm inputs use **Linux ARM64** workstation image `sha256:86c72305ebe2a6397540689e36805f6be92688d797ee97b6610bfd036b6f984d` and native **Codex 0.166.0**. Their original native executable was macOS ARM64; exact accepted-package reproduction checks its registered hash and catalog. A different native platform requires its own explicit configuration and registration.

Download the image, provenance and checksum files from the [accepted-input Release](https://github.com/AI4Collaboration/SwarmHarm/releases/tag/swarmform-accepted-inputs), then run:

```sh
shasum -a 256 -c swarmharm-workstation-linux-arm64-86c72305-SHA256SUMS
docker load --input swarmharm-workstation-linux-arm64-86c72305.tar.gz
```

The accepted-package entry point selects this image from the original registration. It never rebuilds or substitutes it. Install the native dependencies with `scripts/setup-local`; use the [README preparation example](../README.md#accepted-inputs) for an exact tested input. The image archive contains the existing image, with its original OCI identity and attestations.

For the earlier registered Linux amd64 workstation, download the archive,
provenance and checksums from the [workstation Release](https://github.com/AI4Collaboration/SwarmHarm/releases/tag/swarmharm-workstation-linux-amd64-20261106).
Verify the checksums, run `docker load --input swarmharm-workstation-linux-amd64-9ab5b36a.tar.gz`,
and set `SWARMHARM_DOCKER_IMAGE` to the `image` value in `image-provenance.json`.
Fresh builds can have the same runnable contents but a different build-attestation digest.

For a live run, obtain an existing **AxonHub key** with access to the exact model
ID, store it in a file outside the clone, and restrict that file to its owner
(`chmod 600`). Never commit it. Model availability is checked at preparation;
local installation checks do not prove provider access.

Prepare new registrations on an up-to-date `main`. The repository pre-push hook
checks the exact outgoing changes with `scripts/check-ci`. GitHub uses the same
selection and installs only the dependencies it requires. Full regression is an
explicit local option or manual workflow option. Replay published cases from their frozen archives.

Balanced headline example (replace the paths and unique name). Switch the preset,
claim and domain only according to `swarmharm/docs/balanced-study-design.md`; the comparison
flag rejects every other factor difference:

```sh
"$SWARMHARM_HARBOR_ENV/bin/python" swarmharm/run.py \
  --phase prepare --study-mode unified \
  --scenario knowledge-work --component-family unified-delivery \
  --binding-preset records --target-claim coordinated_adverse_outcomes \
  --world-config swarmharm/configs/unified-balanced-envelope.json \
  --comparison-design balanced-headline-v1 \
  --model-id openai/gpt-5.6-sol --population 4 \
  --harness codex --goal-mode off --reasoning-effort high \
  --output /absolute/external/results/new-run \
  --registration-dir swarmharm/registrations/new-run \
  --key-file /absolute/external/axonhub.key
```

By default, commit and push source before preparation, then commit and push the
generated registration. For explicitly local-only work, pass
`--source-retention local` at preparation: commit source locally first, then
commit the generated registration locally. Clean-tree, source, task and input
hash checks remain required; only the remote publication check is omitted.
Launch once with the same output, registration and key paths:

```sh
"$SWARMHARM_HARBOR_ENV/bin/python" swarmharm/launch.py \
  --output /absolute/external/results/new-run \
  --registration-dir swarmharm/registrations/new-run \
  --key-file /absolute/external/axonhub.key
```

See the scenario guide for the other parameter values. Raw outputs must stay
outside the repository; registrations must be direct children of the registration folder.
The launcher reserves host capacity before model calls: by default, at most 16
workstation networks (four concurrent four-agent rollouts). A capacity rejection
leaves the registration unstarted; launch it after another collector finishes.
`SWARMHARM_MAX_WORKSTATION_NETWORKS` may be raised only when the host's Docker
address pools support it. The guard never removes existing networks.
The balanced comparison permits only `records`, `resource` and `grader`, with
the claim mapping in the study design. Other implemented presets require a new
question and separate registration; they are not part of the completed matrix.
For exact reproduction, use the code and registration inside the corresponding
private evidence archive rather than current source.

## Select the condition

SwarmHarm uses `--scenario engineering-capacity` or `--scenario knowledge-work`.
Data and financial analysis are Knowledge Work source workloads. Add
`--workload data-analysis` or `--workload financial-analysis` to select them.
The input-preview, prompt-dump and prepare commands share these selectors.
Historical registrations retain their recorded scenario and source workload.

Select a [runnable setting](../swarmharm/docs/scenarios-and-parameters.md) and its [model/harness route](axonhub-routing.md).
Claude uses **Claude Code** and OpenAI uses **Codex**, both through AxonHub. Preserve the requested
scenario; record any model, harness or persistence change explicitly. Fresh preparation
defaults to `--goal-mode off`. Memory and genuine business-change
notifications remain enabled; explicit native goal modes remain available.
Offline fixtures that skip controls cannot collect live. If an
adapter does not support that scenario, implement and validate it first.

- `--study-mode unified` (default): one end-to-end task with the configured communication surface
  and two separately reported outcome labels.
- `--component-family unified-delivery`: the current common reporting environment.
- `--binding-preset` selects the evaluated interface; `--world-config` supplies
  the four parameter groups. Use the scenario guide's maintained examples.
- Run each threat model in a separate output and registration. The environment
  and task pipeline are shared; models and condition results are not pooled.
  Multiple changed bindings require the operator's `--combined-bindings` flag.
- The task is implemented in `phase2/unified_delivery.py`; domain source work
  lives in `phase2/workload_sources.py` under `swarmharm/`.
- Never reuse an output path or alter a frozen registration.

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
   prompts and executable hashes), and coverage of every check required by the target scenario; every model route is checked afresh. Checks do not establish model behavior.
4. Commit source locally; push first only when using origin source retention. Prepare a fresh registration with the exact model,
   supported harness, goal setting, four-agent population and existing host key.
   Unified inputs always get an exact-configuration path check, including when
   reusing the software checks. Its operator-only result is sealed in
   `phase2.path_validation`; collection recomputes it before inference.
   It also recomputes `phase2.unified_input_contract`, which seals the selected
   interfaces and verifies shared task/tool/file/data bytes at fixed business settings.
5. Commit the registration locally. Verify a clean worktree, matching registration copies and every sealed source/input hash. For origin source retention, also push and verify the remote commit.
6. Launch once. Never edit frozen inputs or retry a whole unfavorable trajectory.

Use `--harness claude-code` for Claude and `--harness codex` for OpenAI; omission
selects the model-family default. Current unified runs use `--goal-mode off`.
Native goal modes and the explicitly authorized Pi comparison are nondefault
conditions that require their own registration. Every adapter version, executable
hash and goal setting is sealed; changed or unknown fields require fresh
validation. See [model and harness routing](axonhub-routing.md) for details.

## Collect and review

Every live call uses AxonHub and preserves model identity through fallback.
Preflight verifies one tool exchange through the selected adapter before subject
work begins. Keep each actor's memory within that rollout. New business state
may prompt continuation; unchanged instructions are not repeated.

Use the frozen time, request and retry limits. Preserve errors, refusals,
corrections, cancellations and incomplete work. Do not alter limits mid-run.

Run the archive's frozen `code/experiments/swarmharm-v1/review.py` against the
completed output, writing a fresh external review. Use the same pinned Python
environment. Preview replay needs no running workstation or custom runtime
search path.
Export ATIF first with the archive's `export_atif.py OUTPUT`. The unified review
then emits `communication-evidence.json` and a readable `communication-transcript.md`,
binding notes and reads to native calls, returned results and ATIF steps.
It also emits the structured `action-monitor.json` and blinded
`transcript-judge-input.json`. Complete the registered semantic review with the
frozen script from the same source/archive:

```bash
python swarmharm/scripts/judge_unified_transcript.py \
  --output /absolute/path/to/completed-output \
  --key-file /absolute/path/to/host-only-axonhub-key
```

The script calls the fixed judge through AxonHub, preserves requests and validated
responses, checks citations against actor/ATIF/event bindings, and writes the
verdict. It never replaces existing final outputs. Failed responses and incomplete
streams are not saved verbatim: diagnostics retain bounded hashes, HTTP status,
restricted categories, request-ID presence and a digest of a validated ID. A fixed
classifier records an explicitly stated provider refusal; `unknown` does
not mean the provider did not refuse. Exact failed-response text is irrecoverable
from these diagnostics; use authorized gateway logs if more detail is needed.
Existing frozen evaluations retain their original scripts and evidence.

Review full native requests, exact reads, authored messages, later actions,
terminal files and ATIF-v1.8 continuity. Independently reconstruct effects from
protected evidence. Preview, acceptance and self-report are not final outcomes.
Preserve each source case's evidence limits; do not stitch different cases into
one chain. Keep current findings in README and evidence indexes, with raw
trajectories in linked releases.

## SwarmForm cache rollout

The following settings reproduce the reviewed four-agent v57 pilot. Use the normal preparation and collection flow above with
`--scenario knowledge-work --binding-preset control --target-claim autonomous_formation` and
`--world-config swarmharm/configs/swarmform-work-cache.json`.
Omit `--comparison-design`; that option selects the separate SwarmHarm comparison.
The permitted model comparisons are `openai/gpt-5.6-sol` and `openai/gpt-6.1-sol`,
each with four agents, native Codex, high reasoning and goal off. Freeze and
run each registration once. The primary result measures communication. Inspect
convention adoption and the separately registered sustained-exchange measures.
