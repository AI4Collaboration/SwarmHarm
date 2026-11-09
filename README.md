# SwarmForm

**Can agents in separate workspaces discover one another and build a communication channel on their own?** We test whether they keep using that channel as new work arrives.

The delivery matrix is **5 shared deployments × 5 encoding opportunities × 2 domains = 50 input environments**: 25 Knowledge Work and 25 Engineering. Both domains receive full coverage; all existing inputs and results from the four-domain catalog remain available. Each uses three independent agents, private source material, persistent memory and three business intakes. Tasks give no peer roster, communication method or cooperation instruction. Current runs use Sol 6.1 with native Codex through AxonHub, high reasoning and goal off.

## Accepted inputs

[Download accepted inputs](https://github.com/AI4Collaboration/SwarmHarm/releases/download/swarmform-accepted-inputs/swarmform-main-inputs.zip) · [Release](https://github.com/AI4Collaboration/SwarmHarm/releases/tag/swarmform-accepted-inputs)

The current bundle contains **10 accepted inputs out of the 50-input target**, each with reviewed sustained three-agent exchange. The [four-domain bundle](https://github.com/AI4Collaboration/SwarmHarm/releases/download/swarmform-accepted-inputs/swarmform-inputs.zip) is preserved. New exports select the current scope; add `--all-retained` to include supplemental results. Its index links each set of three Harbor tasks to its tested source, settings, observed exchange, business scores and full trajectory. Use `python3 scripts/export_swarmform_input_matrix.py --accepted --output ../accepted-inputs` with the installed runtime to reproduce it from Git.

Knowledge Work agents have independently published source appendices, adopted each other’s convention and reused revised documents across three intakes, producing nine correct deliveries. Archive and job-service cases also show sustained exchange. Engineering tests whether formation extends to executable artifact work. Data Analysis and Financial Analysis remain supplemental evidence.

## Continue from main

Run `python3 scripts/check_swarmform_inputs.py --status` from a checkout of `main`. It summarizes admitted inputs, reviewed behavior, active work and the next cell from the [matrix ledger](docs/live-rollout-status.json). For a reviewed case, follow its trajectory link. For an active run, check its completion record before starting anything. Record the next verified result in the same ledger and push it to `main`.

The remaining inputs include agents knowingly publishing partial work, sharing only records irrelevant to peers, or leaving the third worker disconnected. Clear partial-coverage receipts did not by themselves bring the third worker into an exchange. Making local processors visible also did not establish exchange. The target is sustained substantive communication by three agents. They may question or reject what they receive; adopting a method and improving business output are separate results. A functional environment can also be delivered with a negative result after seven substantive refinements and reviewed retests. [Acceptance criteria](docs/formation-study-design.md#deliverables-and-acceptance-criteria)

## Generate and inspect inputs

Use Python 3.12. For Docker validation, first run `bash scripts/setup-local` and source the environment file it prints.

```sh
python3 scripts/check_swarmform_inputs.py
python3 scripts/export_swarmform_input_matrix.py --output ../swarmform-input-matrix
python3 scripts/check_swarmform_input_runners.py --cell "shared_ipc/payload_content/Knowledge Work"
```

By default the exporter writes the 50 selected packages with 150 Harbor tasks, exact prompts and tools, private arrivals, protected truth and file hashes. `--all-retained` exports the full 100-input catalog. The smaller scope changes selection only; frozen inputs and original scores stay intact. The runner command shows how to validate an individual input without a model call. [Preparing a model rollout](docs/formation-study-design.md#collecting-an-admitted-input)

**Keep validation lightweight:** check each transport mechanism once, then the selected business outputs and isolation conditions. `python3 scripts/check-ci --plan` shows checks selected from your changes against `origin/main`. Local push and GitHub use that same selection and run each check once. Documentation needs no Docker or harness installation; operator-witness edits skip historical replay. Use `--full` only for an intentional complete regression. Prior SwarmHarm inputs, successful cases and scores remain available in the [research archive](docs/research/README.md).
