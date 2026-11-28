# SwarmForm and SwarmHarm

> ## Pending / Additional Rollouts to Collect (Sync to HF Bucket `ai4collaboration/swarmharm-rollout`)
>
> The 11-model multi-agent SwarmHarm matrix (`N = 4, 16, 32`) currently has **395 / 396** completed runs in `ai4collaboration/swarmharm-rollout`. **Two follow-up collections are needed** to answer *"Do swarms misalign agents?"* and close the final missing cell:
>
> ### 1. Required — Single-Agent Baseline (`N = 1`, 11 models × 12 inputs = 132 runs / 132 trajectories)
> Runs the exact same 12 SwarmHarm environments, tools, and prompts with **only 1 agent (`N = 1`, zero peers)** so we can directly compare single-agent misbehavior vs. multi-agent (`N = 4, 16, 32`) rates across all 6 failure modes and 11 models.
>
> ```sh
> # Preview plan (132 single-agent cohorts across all 11 models)
> python3.12 scripts/run-evals --studies swarmharm --populations 1 --skip-api-check --out ../swarm-runs-n1
>
> # Execute single-agent baseline (writes swarmharm/<model>/<slug>/n1/...; safe to merge into HF bucket alongside n4/n16/n32)
> python3.12 scripts/run-evals --studies swarmharm --populations 1 --skip-api-check --out ../swarm-runs-n1 --execute
> ```
>
> - **Bucket overwrite/merge behavior**: Outputs live under `swarmharm/<model>/<model-slug>/n1/...`. Syncing `../swarm-runs-n1/swarmharm/` into `ai4collaboration/swarmharm-rollout/swarmharm/` adds `n1/` cleanly without overwriting any existing `n4/`, `n16/`, or `n32/` trajectories.
> - **Optional matched uncoupled baseline (`N = 4`, 4 independent isolated agents per cell)**: `--coupling uncoupled` is now strictly matched to the `v22` main inputs (identical `access`/`verification`/`observation`; only `coupling.{discussion,published_packs,resource_pool}=per_account`):
>   ```sh
>   python3.12 scripts/run-evals --studies swarmharm --populations 4 --coupling uncoupled --skip-api-check --out ../swarm-runs-uncoupled --execute
>   ```
>
> ### 2. Required — Missing 1/396 Cell (`Gemini 4 Argon`, `N = 32`, Knowledge Work `task-gaming`)
> The only remaining incomplete cell from the `N = 4, 16, 32` matrix (prior run ended in `provider_hold`). Re-running completes **396 / 396**:
>
> ```sh
> python3.12 scripts/run-evals --studies swarmharm --models argon --populations 32 \
>   --scenarios knowledge-work --mechanisms task-gaming --skip-api-check --out ../swarm-runs-argon-fix --execute
> ```
>
> - **Bucket overwrite/merge behavior**: Upload the completed `swarmharm/argon/google-gemini-4-argon/n32/knowledge-work-task-gaming-r1-*` directory into `ai4collaboration/swarmharm-rollout/swarmharm/argon/google-gemini-4-argon/n32/` to replace/supplement the `provider_hold` attempt.

| Study | Research question | Current inputs |
| --- | --- | --- |
| [SwarmForm](swarmform/README.md) | When do independent agents establish two-way communication, and what coordination structures emerge? | [30 software problems and one separate open mathematics problem](swarmform/inputs.json) |
| [SwarmHarm](swarmharm/README.md) | How do actions across reporting desks combine or propagate, and what consequences follow? | [12 environment configurations and their participant assignments](swarmharm/inputs.json) |

<a id="swarmform"></a>

Both studies use cohort sizes of **4, 8, 16 and 32 agents**.

**SwarmForm** pairs each software problem with three information conditions. A separate choice selects direct communication, shared files, mapped memory or a socket-backed project store. [Environment source](rollouts/swarmform/formation_inputs.py) · [Latest formation results](swarmform/docs/formation-readiness.json)

<a id="swarmharm"></a>

**SwarmHarm** applies six reporting-system configurations to engineering and knowledge work. Each participant receives a customer assignment. [Environment source](swarmharm/phase2/mechanism_inputs.py) · [Reviewed cases](swarmharm/docs/research/overview.md)

## Run one study

### SwarmForm with your own API

On a host with Git, Python 3.12 and a running Linux Docker engine, supply an OpenAI-compatible Chat Completions endpoint with function tools. Set the model ID when the endpoint serves multiple models or omits `/models`. The first collection installs the Python client and builds the pinned software workstations. No provider-specific CLI or account is required.

```sh
git clone --depth 1 https://github.com/AI4Collaboration/SwarmHarm.git
cd SwarmHarm
export OPENAI_BASE_URL='https://your-provider.example/v1'
export OPENAI_API_KEY='your-provider-key'
export OPENAI_MODEL='your-served-model-id'
scripts/run-swarmform --tasks pb-ctags-possible --channels filesystem --populations 4 --out ../swarmform-first --execute
```

Omit `--execute` to preview. For all 480 software cohorts, run `scripts/run-swarmform --execute --out ../swarmform-main`. The model and input settings are recorded with every cohort. [SwarmForm guide](swarmform/README.md#running)

### Registered lineup

Preview either study with `python3.12 scripts/run-evals --studies swarmform` or `--studies swarmharm`. To collect, run `bash scripts/setup-defaults`, set `OPENAI_BASE_URL` and `OPENAI_API_KEY`, and add `--execute`. The preflight checks the models scheduled for the selected study. [Installation and collection](docs/running-evals.md) · [Model names](docs/model-lineup.md)

<a id="research-framework"></a>
<a id="evidence"></a>
<a id="accepted-inputs"></a>
<a id="codebase-audit"></a>

Each study owns its inputs and results. [SwarmForm coverage](swarmform/docs/formation-readiness.json) · [SwarmHarm input ledger](swarmharm/docs/research/mechanism-input-status.json) · [Research archive](docs/research/README.md)
