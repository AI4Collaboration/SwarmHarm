# SwarmForm and SwarmHarm

| Study | Research question | Current inputs |
| --- | --- | --- |
| [SwarmForm](swarmform/README.md) | When do independent agents establish two-way communication, and what coordination structures emerge? | [30 software problems and one separate open mathematics problem](swarmform/inputs.json) |
| [SwarmHarm](swarmharm/README.md) | How do actions across reporting desks combine or propagate, and what consequences follow? | [12 environment configurations and their participant assignments](swarmharm/inputs.json) |

<a id="swarmform"></a>

**SwarmForm** pairs each software problem with three information conditions. A separate choice selects direct communication, shared files, mapped memory or a socket-backed project store. [Environment source](rollouts/swarmform/formation_inputs.py) · [Latest formation results](swarmform/docs/formation-readiness.json)

<a id="swarmharm"></a>

**SwarmHarm** applies six reporting-system configurations to engineering and knowledge work. Each participant receives a customer assignment. [Environment source](swarmharm/phase2/mechanism_inputs.py) · [Reviewed cases](swarmharm/docs/research/overview.md)

## Run one study

Preview from the repository root. The commands below make zero model calls.

```sh
python3.12 scripts/run-evals --studies swarmform
python3.12 scripts/run-evals --studies swarmharm
```

For the full SwarmForm software matrix use the [study-specific command](swarmform/README.md#running). For collection using an OpenAI-compatible endpoint, run `bash scripts/setup-defaults`, set `OPENAI_BASE_URL` and `OPENAI_API_KEY`, and add `--execute` to the selected study command. Keep API credentials and raw trajectories outside Git. [Installation and collection](docs/running-evals.md) · [Model names](docs/model-lineup.md)

<a id="research-framework"></a>
<a id="evidence"></a>
<a id="accepted-inputs"></a>
<a id="codebase-audit"></a>

Each study owns its inputs and results. [SwarmForm coverage](swarmform/docs/formation-readiness.json) · [SwarmHarm input ledger](swarmharm/docs/research/mechanism-input-status.json) · [Research archive](docs/research/README.md)
