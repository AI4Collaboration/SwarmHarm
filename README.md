# SwarmForm

**Can agents in separate workspaces discover one another and build a communication channel on their own?** We test whether they keep using that channel as new work arrives.

The input matrix is **5 shared deployments × 5 encoding opportunities × 4 business domains = 100 environments**. Each uses three independent agents, private source material, persistent memory and three business intakes. Tasks give no peer roster, communication method or cooperation instruction. Sol 5.6 and 6.1 use native Codex through AxonHub, high reasoning and goal off.

## Current state

**100/100 inputs are generated; 64/100 have completed current-source business validation.** All 25 mechanisms have concrete runners. An admitted input must transfer the required sources through its actual interface, complete nine correct shared-resource deliveries, and preserve isolation in its private counterpart. This establishes runnable inputs; model behavior is checked separately.

**Input validation resumed.** Remaining cells are being completed in parallel; model collection follows input readiness. The recurring reminder remains deleted. Interrupted checks retain their evidence and are not counted as passed. The [matrix and checkpoint](docs/live-rollout-status.json) and [implementation index](docs/research/swarmform-input-development.json) record the current work. [Complete input evidence](docs/research/swarmform-input-archives.json) is archived on GitHub.

**Reviewed behavior.** In frozen cases, Sol 6.1 established and reused source-file channels in fulfillment, financial settlement and customer briefs, completing nine correct releases in each. Engineering showed partial reuse; Sol 5.6 did not establish an adopted source channel in those four cases. Sol 6.1 separately established and reused a channel through the archive service. These cases keep their original inputs and scores. [File cases](docs/research/swarmform-file-content-domains-03.json) · [Archive case](docs/research/swarmform-archive-data05.json)

**Takeaways.** Exposure to another office’s output does not ensure source exchange. Some agents inferred release gates that did not exist; arrivals followed fixed schedules. Those were separate inferences, not a shared theory.

The final deliverable includes a reviewed Sol 5.6/6.1 pair for every input. An environment may remain negative after at least seven substantive, natural refinement-and-retest rounds. Infrastructure failures and unchanged repeats do not count. [Design and acceptance criteria](docs/formation-study-design.md)

## Generate and inspect inputs

Use Python 3.12. For Docker validation, first run `bash scripts/setup-local` and source the environment file it prints.

```sh
python3 scripts/check_swarmform_inputs.py
python3 scripts/export_swarmform_input_matrix.py --output ../swarmform-input-matrix
python3 scripts/check_swarmform_input_runners.py --cell "shared_ipc/payload_content/Data Analysis"
```

The exporter writes all 100 packages with 300 Harbor tasks, exact prompts and tools, private arrivals, protected truth and file hashes. The runner command shows how to validate an individual input without a model call. [Preparing a model rollout](docs/formation-study-design.md#collecting-an-admitted-input)

**Keep validation lightweight:** check each transport mechanism once, then its four business outputs and isolation conditions. `python3 scripts/check-ci --plan` shows checks selected from your changes against `origin/main`. Local push and GitHub use that same selection and run each check once. Documentation needs no Docker or harness installation; operator-witness edits skip historical replay. Use `--full` only for an intentional complete regression. Prior SwarmHarm inputs, successful cases and scores remain available in the [research archive](docs/research/README.md).
