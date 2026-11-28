# SwarmForm and SwarmHarm

> ## Pending / Additional Rollouts to Collect (Target HF Bucket: `ai4collaboration/swarmharm-rollout`)
>
> **Audited bucket status (`ai4collaboration/swarmharm-rollout`):**
> - **Already complete (`527 / 528` across `N = 4, 8, 16, 32`):** All 11 models have complete reviewed runs for `n4` (132/132), `n8` (132/132), `n16` (132/132), and `n32` (131/132), all collected with **`--reasoning-effort medium`**.
> - **Target final bucket (`660 / 660`):** 11 models × 5 populations (`n1`, `n4`, `n8`, `n16`, `n32`) × 12 inputs = **660 completed runs** (`n64` is retired and empty; do not collect `N=64`).
> - **Exact remaining work = `133` runs** (pass the same `--model-map` used for the existing 527 runs so `astra` → `openai/gpt-6.2-astra`, `sol` → `openai/openai/gpt-6.2-sol`, `argon` → `gcp/google/gemini-4-argon`, etc., and **`--reasoning-effort medium`** to match the existing bucket):
>
> ### 1. Required — Single-Agent Baseline (`N = 1`, 11 models × 12 inputs = 132 runs / 132 trajectories)
> Runs the exact same 12 SwarmHarm environments, tools, and prompts with **1 agent (`N = 1`, zero peers)** to answer *"Do swarms misalign agents?"* directly.
>
> ```sh
> # Preview plan (132 single-agent runs across all 11 models at reasoning_effort=medium)
> python3.12 scripts/run-evals --studies swarmharm --populations 1 --reasoning-effort medium \
>   --model-map /path/to/model-map.json --skip-api-check --out ../swarm-runs-n1
>
> # Execute single-agent baseline
> python3.12 scripts/run-evals --studies swarmharm --populations 1 --reasoning-effort medium \
>   --model-map /path/to/model-map.json --skip-api-check --out ../swarm-runs-n1 --execute
> ```
>
> ### 2. Required — Missing 1/528 Cell (`Gemini 4 Argon`, `N = 32`, Knowledge Work `task-gaming`)
> The **only** incomplete run across all 528 `N = 4, 8, 16, 32` runs (prior run hit `provider_hold` / `provider_filter_final`). Completing it brings `n4/n8/n16/n32` to **528 / 528**:
>
> ```sh
> python3.12 scripts/run-evals --studies swarmharm --models argon --populations 32 \
>   --scenarios knowledge-work --mechanisms task-gaming --reasoning-effort medium \
>   --model-map /path/to/model-map.json --skip-api-check --out ../swarm-runs-argon-n32-fix --execute
> ```
>
> ### Bucket Upload / Overwrite Rules (CRITICAL — DO NOT WIPE EXISTING `n4/n8/n16/n32`)
> Because bucket sync tools can overwrite matching paths:
> 1. **Never use `--delete` on the bucket root**, and **never overwrite** the existing `swarmharm/<model>/index.json` or `plan.json` (which index `n4/n8/n16/n32`) with an `n1`-only or 1-cell index file.
> 2. **For `N = 1` (132 runs):** upload only the new **`swarmharm/<model>/<model-slug>/n1/`** directories into `ai4collaboration/swarmharm-rollout/swarmharm/<model>/<model-slug>/n1/` (plus optional `n1-plan.json` / `n1-index.json` so existing `index.json` stays intact, or merge the 12 `n1` rows into each model's `index.json`).
> 3. **For `Argon N = 32 KW task-gaming` (1 run):** upload the completed `knowledge-work-task-gaming-r1-*` folder into `ai4collaboration/swarmharm-rollout/swarmharm/argon/google-gemini-4-argon/n32/` (replacing/overwriting the failed `provider_hold` attempt) and update that single entry in `swarmharm/argon/index.json`.
> 4. **Optional matched uncoupled baseline (`N = 4 --coupling uncoupled`):** fixed to match `v22` coupled inputs on every non-coupling parameter (`access`/`verification`/`observation`); run into a separate `--out ../swarm-runs-uncoupled` if needed.

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
