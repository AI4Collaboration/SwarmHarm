# SwarmForm

**Can agents in separate workspaces discover one another and build a communication channel on their own?** We test whether they keep using that channel as new work arrives.

The main matrix is **5 shared deployments × 5 encoding opportunities = 25 Knowledge Work environments**. Engineering adds **5 generalization environments**, one payload-content configuration per deployment. The delivery target is **30 inputs**; all existing inputs and results from the four-domain catalog remain available. Each uses three independent agents, private source material, persistent memory and three business intakes. Tasks give no peer roster, communication method or cooperation instruction. Current runs use Sol 6.1 with native Codex through AxonHub, high reasoning and goal off.

## Accepted inputs

[Download the input bundle](https://github.com/AI4Collaboration/SwarmHarm/releases/download/swarmform-accepted-inputs/swarmform-inputs.zip) · [Release](https://github.com/AI4Collaboration/SwarmHarm/releases/tag/swarmform-accepted-inputs)

The linked retained bundle contains verified inputs across the four domains. New exports select the current 30-input scope; add `--all-retained` to include supplemental results. Its index links each set of three Harbor tasks to its tested source, settings, observed exchange, business scores and full trajectory. Use `python3 scripts/export_swarmform_input_matrix.py --accepted --output ../accepted-inputs` with the installed runtime to reproduce it from Git.

Knowledge Work agents have independently published source appendices, adopted each other’s convention and reused revised documents across three intakes, producing nine correct deliveries. Archive and job-service cases also show sustained exchange. Engineering tests whether formation extends to executable artifact work. Earlier Data Analysis, Financial Analysis and other Engineering cases remain supplemental evidence.

## Continue from main

Run `python3 scripts/check_swarmform_inputs.py --status` from a checkout of `main`. It summarizes admitted inputs, reviewed behavior, active work and the next cell from the [matrix ledger](docs/live-rollout-status.json). For a reviewed case, follow its trajectory link. For an active run, check its completion record before starting anything. Record the next verified result in the same ledger and push it to `main`.

The remaining inputs include agents stopping at local partial work, publishing only records irrelevant to peers, or leaving the third worker disconnected. The target is sustained, useful exchange by three agents. A functional environment can also be delivered with a negative result after seven substantive refinements and reviewed retests. [Acceptance criteria](docs/formation-study-design.md#deliverables-and-acceptance-criteria)

## Generate and inspect inputs

Use Python 3.12. For Docker validation, first run `bash scripts/setup-local` and source the environment file it prints.

```sh
python3 scripts/check_swarmform_inputs.py
python3 scripts/export_swarmform_input_matrix.py --output ../swarmform-input-matrix
python3 scripts/check_swarmform_input_runners.py --cell "shared_ipc/payload_content/Knowledge Work"
```

By default the exporter writes the 30 selected packages with 90 Harbor tasks, exact prompts and tools, private arrivals, protected truth and file hashes. `--all-retained` exports the full 100-input catalog. The smaller scope changes selection only; frozen inputs and original scores stay intact. The runner command shows how to validate an individual input without a model call. [Preparing a model rollout](docs/formation-study-design.md#collecting-an-admitted-input)

**Keep validation lightweight:** check each transport mechanism once, then its four business outputs and isolation conditions. `python3 scripts/check-ci --plan` shows checks selected from your changes against `origin/main`. Local push and GitHub use that same selection and run each check once. Documentation needs no Docker or harness installation; operator-witness edits skip historical replay. Use `--full` only for an intentional complete regression. Prior SwarmHarm inputs, successful cases and scores remain available in the [research archive](docs/research/README.md).
