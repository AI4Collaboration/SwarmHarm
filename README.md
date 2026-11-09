# SwarmForm

**Can agents in separate workspaces discover one another and build a communication channel on their own?** We test whether they keep using that channel as new work arrives.

The input matrix is **5 shared deployments × 5 encoding opportunities × 4 business domains = 100 environments**. Each uses three independent agents, private source material, persistent memory and three business intakes. Tasks give no peer roster, communication method or cooperation instruction. Current runs use Sol 6.1 with native Codex through AxonHub, high reasoning and goal off.

## Accepted inputs

[Download the input bundle](https://github.com/AI4Collaboration/SwarmHarm/releases/download/swarmform-accepted-inputs/swarmform-inputs.zip) · [Release](https://github.com/AI4Collaboration/SwarmHarm/releases/tag/swarmform-accepted-inputs)

The bundle contains the verified final input for each included environment. Its index links each set of three Harbor tasks to its tested source, settings, observed exchange, business scores and full trajectory. Use `python3 scripts/export_swarmform_input_matrix.py --accepted --output ../accepted-inputs` with the installed runtime to reproduce it from Git.

Across the four business domains, archive-service agents independently exchanged sources across intakes and produced nine correct deliveries in each domain. In Financial Analysis, agents used job metadata to exchange 130,835 useful bytes and completed all nine reports. In Engineering, agents created and reused calibration-source files across three intakes; all nine releases independently matched the required data.

## Continue from main

Run `python3 scripts/check_swarmform_inputs.py --status` from a checkout of `main`. It summarizes admitted inputs, reviewed behavior, active work and the next cell from the [matrix ledger](docs/live-rollout-status.json). For a reviewed case, follow its trajectory link. For an active run, check its completion record before starting anything. Record the next verified result in the same ledger and push it to `main`.

The remaining inputs include agents stopping at local partial work, publishing only records irrelevant to peers, or leaving the third worker disconnected. The target is sustained, useful exchange by three agents. A functional environment can also be delivered with a negative result after seven substantive refinements and reviewed retests. [Acceptance criteria](docs/formation-study-design.md#deliverables-and-acceptance-criteria)

## Generate and inspect inputs

Use Python 3.12. For Docker validation, first run `bash scripts/setup-local` and source the environment file it prints.

```sh
python3 scripts/check_swarmform_inputs.py
python3 scripts/export_swarmform_input_matrix.py --output ../swarmform-input-matrix
python3 scripts/check_swarmform_input_runners.py --cell "shared_ipc/payload_content/Data Analysis"
```

The exporter writes all 100 packages with 300 Harbor tasks, exact prompts and tools, private arrivals, protected truth and file hashes. The runner command shows how to validate an individual input without a model call. [Preparing a model rollout](docs/formation-study-design.md#collecting-an-admitted-input)

**Keep validation lightweight:** check each transport mechanism once, then its four business outputs and isolation conditions. `python3 scripts/check-ci --plan` shows checks selected from your changes against `origin/main`. Local push and GitHub use that same selection and run each check once. Documentation needs no Docker or harness installation; operator-witness edits skip historical replay. Use `--full` only for an intentional complete regression. Prior SwarmHarm inputs, successful cases and scores remain available in the [research archive](docs/research/README.md).
