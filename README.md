# SwarmForm and SwarmHarm

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
