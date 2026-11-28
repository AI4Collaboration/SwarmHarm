# SwarmForm and SwarmHarm

> ## Agent Rollout Handoff — Exact Pending SwarmHarm Runs (`ai4collaboration/swarmharm-rollout`)
>
> **STOP AND READ FIRST — DO NOT RE-RUN COMPLETED MULTI-AGENT COHORTS:**
> - **Already complete in HF bucket `ai4collaboration/swarmharm-rollout` (`527 / 528` runs):** All 11 models already have complete, reviewed runs for **`n4` (132/132)**, **`n8` (132/132)**, **`n16` (132/132)**, and **`n32` (131/132)**, all collected at **`--reasoning-effort medium`**.
> - **DO NOT run** `N = 4, 8, 16, 32` again (except the single missing Argon cell below). **DO NOT run `N = 64`** (`n64` is retired; ignore the empty `sonnet`/`haiku` `n64/` dirs).
> - **Final target bucket state:** **660 / 660 completed runs** = 11 models × 5 populations (`n1`, `n4`, `n8`, `n16`, `n32`) × 12 inputs.
> - **Exact remaining work to run now = `133` runs** (use **`--reasoning-effort medium`** and the exact `--model-map` below so served models match the existing 527 runs):
>
> ### Model map matching the existing 527 bucket runs (`model-map.json`)
> ```json
> {
>   "astra": "openai/gpt-6.2-astra",
>   "sol": "openai/openai/gpt-6.2-sol",
>   "terra": "openai/gpt-6.1-terra",
>   "luna": "openai/gpt-6-luna",
>   "opus": "azure/anthropic/claude-opus-5-5",
>   "sonnet": "aws/anthropic/bedrock-claude-sonnet-5-5",
>   "haiku": "azure/anthropic/claude-haiku-5-5",
>   "argon": "gcp/google/gemini-4-argon",
>   "kimi": "moonshotai/kimi-k3.1-pro",
>   "glm": "z-ai/glm-5.3",
>   "deepseek": "deepseek/deepseek-v4.1-flash-1017"
> }
> ```
> *(Adjust provider prefixes only if your endpoint spells the same served model differently; keep the underlying model versions identical.)*
>
> ### Task 1 (Required) — Single-Agent Baseline (`N = 1`, 132 runs, high concurrency `-j 12`)
> Runs the exact same 12 SwarmHarm inputs with **1 agent (`N = 1`, zero peers)** to test whether models misbehave alone (`"Do swarms misalign agents?"`). `--concurrency 12` runs all 12 `N = 1` cohorts per model in parallel (serialized git commits, auto-scaled Docker network capacity):
>
> ```sh
> # 1. Preview plan (must show swarmharm: 132, reasoning: medium, populations: [1])
> python3.12 scripts/run-evals --studies swarmharm --populations 1 --concurrency 12 \
>   --reasoning-effort medium --model-map /path/to/model-map.json --skip-api-check --out ../swarm-runs-n1
>
> # 2. Execute all 132 single-agent baseline runs
> python3.12 scripts/run-evals --studies swarmharm --populations 1 --concurrency 12 \
>   --reasoning-effort medium --model-map /path/to/model-map.json --skip-api-check --out ../swarm-runs-n1 --execute
> ```
>
> ### Task 2 (Required) — Missing 1/528 Cell (`Gemini 4 Argon`, `N = 32`, Knowledge Work `task-gaming`)
> The **only** missing/failed run across all 528 `N = 4, 8, 16, 32` runs (prior attempt ended in `provider_hold` / `provider_filter_final`):
>
> ```sh
> python3.12 scripts/run-evals --studies swarmharm --models argon --populations 32 \
>   --scenarios knowledge-work --mechanisms task-gaming --reasoning-effort medium \
>   --model-map /path/to/model-map.json --skip-api-check --out ../swarm-runs-argon-n32-fix --execute
> ```
>
> ### HF Bucket Sync / Overwrite Rules (CRITICAL)
> When uploading to `ai4collaboration/swarmharm-rollout`:
> 1. **NEVER run `--delete` on the bucket root**, and **NEVER overwrite** the existing `swarmharm/<model>/index.json` or `plan.json` (which index the completed `n4/n8/n16/n32` runs) with an `n1`-only or 1-cell file.
> 2. **For Task 1 (`N = 1`):** upload only each model's new **`swarmharm/<model>/<model-slug>/n1/`** subtree into `ai4collaboration/swarmharm-rollout/swarmharm/<model>/<model-slug>/n1/` (and either merge the 12 `n1` rows into each model's existing `index.json` or save separately as `index-n1.json`). Zero existing `n4/n8/n16/n32` files are touched.
> 3. **For Task 2 (`Argon N = 32 KW task-gaming`):** overwrite/replace the single failed `knowledge-work-task-gaming-r1-*` directory under `ai4collaboration/swarmharm-rollout/swarmharm/argon/google-gemini-4-argon/n32/` and update that single row in `swarmharm/argon/index.json`.
> 4. **Verify final bucket:** every one of the 11 models has 12 completed reviewed runs in each of `n1/`, `n4/`, `n8/`, `n16/`, `n32/` (**60 per model = 660 total**).

---

| Study | Research question | Current inputs |
| --- | --- | --- |
| [SwarmForm](swarmform/README.md) | When do independent agents establish two-way communication, and what coordination structures emerge? | [30 software problems and one separate open mathematics problem](swarmform/inputs.json) |
| [SwarmHarm](swarmharm/README.md) | How do actions across reporting desks combine or propagate, and what consequences follow? | [12 environment configurations and their participant assignments](swarmharm/inputs.json) |

<a id="swarmform"></a>

SwarmForm uses cohort sizes of **4, 8, 16 and 32 agents**. SwarmHarm uses **1 (single-agent baseline), 4, 8, 16 and 32 agents**.

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

### SwarmHarm & registered lineup

To set up dependencies on a fresh host, run `bash scripts/setup-defaults` and set `OPENAI_BASE_URL` / `OPENAI_API_KEY` (or `OPENROUTER_API_KEY`). For SwarmHarm, **do not re-run the already-collected `N = 4, 8, 16, 32` matrix**; run only the pending 133 runs listed in the handoff box at the top of this page (or pass explicit `--populations`, `--models`, `--scenarios`, `--mechanisms` for a targeted study). [SwarmHarm guide](swarmharm/README.md) · [Installation and collection](docs/running-evals.md) · [Model names](docs/model-lineup.md)

<a id="research-framework"></a>
<a id="evidence"></a>
<a id="accepted-inputs"></a>
<a id="codebase-audit"></a>

Each study owns its inputs and results. [SwarmForm coverage](swarmform/docs/formation-readiness.json) · [SwarmHarm input ledger](swarmharm/docs/research/mechanism-input-status.json) · [Research archive](docs/research/README.md)
