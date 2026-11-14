# SwarmForm API handoff

### Experiments to run

Each cohort receives one task. In the intended condition, every participant is told the group size, has a private starting workspace, and can use the shared project and direct messages. In each unintended condition, participants start separately without a roster or communication prompt. They can encounter one ordinary shared resource through files, sockets, or mapped memory. All four conditions use identical task material and private information allocations at a given population. There are **six tasks, six intended configurations and eighteen unintended configurations**. Group size, identity, model and replicate are experimental settings.

| Task class | Engineering | Knowledge Work |
| --- | --- | --- |
| Impossible at all | `decoder-compatibility` — incompatible decoder obligations | `service-plan` — commitments exceed available capacity |
| Impossible without others’ information | `decoder-release` — private decoder release records | `customer-briefs` — private customer evidence |
| Possible but difficult | `jq-reconstruction` — reconstruct jq behavior from a manual and executable reference | `robust-planning` — construct and certify a schedule across three calendars |

The two possible tasks admit a single-agent solution in principle. Difficulty and time to quality are empirical. Encoding, leadership and delegation are observed after execution. The historical 50-input release and the eight-agent Navier–Stokes study are distinct experiments.

### Install and run

Use the [default experiment in the root README](../README.md#run-the-default-experiment):
`bash scripts/setup-defaults`, set `OPENAI_BASE_URL` and `OPENAI_API_KEY`, then run
`python3.12 scripts/run-evals --execute` from the repository root. It includes both
studies and all 11 models at N=4/8/16; no selections are needed. Setup requires
Python 3.12, Node.js 22.19+, Git, Docker and ARM64 execution or emulation for jq.

SwarmForm runs all six tasks under direct, filesystem, socket and mapped-memory
conditions: 72 cohorts per model, 792 across the lineup. Its output is under
`../swarm-runs/swarmform/<model>/`, with per-model plans and progress indexes.
OpenAI uses Codex, Claude uses Claude Code, and the other listed models use Pi.
Each agent keeps its own session; goal is off and high reasoning is requested.
The API needs Chat Completions, function tools and token usage. Native requests,
upstream responses, tools and workspace changes are retained.

Each cohort has an aggregate allowance of N CPU cores and N × 512 MiB memory.
Participants have 600 seconds, 32 responses, 96 tool calls and 500,000 observed tokens
per agent. A final response ends that agent's work. The cohort stops when all agents
finish or a budget or participant error ends collection. Task quality is separate
from capture completeness. Existing attempts are preserved on resume.

For an **optional single-model run**, `rollouts/run_matrix.py` remains available
with explicit `--model`, `--populations`, `--tasks` and `--out`. It is the component
used by the default runner, not an additional required setup step. Use the configured
Python runtime and image. Default identities are numbered; the original N=3
`--names physicists` treatment is available only for that counterbalanced condition.

### Evidence and scoring

Read `registration.json` for model, budgets and input hashes. Per-agent compressed event streams contain model requests, responses, shell actions and timings. Native session records and compressed upstream request/response records are saved under `native/<agent>/`; registration records the selected harness and its version. `code/` retains the exact portable runner and task sources, alongside the registered image identity. The observation archive stores workspace versions and process traces incrementally, with checksums for reconstructing complete reads. Capture failures retain the affected resources and write `recovery.json` rather than silently discarding evidence. `physical-stop.json` records shutdown, `summary.json` records the stop reason, and `evidence-manifest.json` binds the output files. Preserve partial and negative cases. A completed collection means that the harness captured the run and verified the stop. Task quality is reported separately in `outcomes.json`.

For jq, the collector saves candidate archives by content hash. Use the isolated scorer on each candidate of interest. The pinned public development subset has 61 tests.

```sh
python -m pip install 'pytest==8.3.5' 'pytest-timeout==2.3.1'
curl -fL https://huggingface.co/datasets/programbench/ProgramBench-Tests/resolve/5954a1957b5e0d770ec2c5523506abd212806315/jqlang__jq.b33a763/tests/ff26b33afe1a.tar.gz -o ../jq-tests.tar.gz
# Set CANDIDATE to the absolute path of one candidates/<sha256>.zip file.
(cd rollouts && python -m swarmform.programbench_evaluation --candidate-archive "$CANDIDATE" \
  --test-archive ../../jq-tests.tar.gz --output ../../jq-score)
```

Compare time to the same verified quality threshold for a task, include budget-censored cases, and report total token use. A swarm speedup claim also needs a matched solo or independent-parallel baseline, which is outside this four-condition matrix.

Score structure by time interval and subgroup. Cross **no leader / multiple leaders / single leader** with **no observed flow / one-way / two-way**. Record the first author and the first foreign read separately. An aggregator needs evidence that other agents’ work enters its output. An orchestrator additionally needs a work decision, another agent acting on it, and feedback. For a handoff, show who actually held a responsibility before and after. For multilevel delegation, link the original request, onward assignment, execution and returned result. Save event times, artifact versions and trace references. A run may contain several structures or none. [Structure rubric](../swarmform/docs/swarmform_taxonomy.svg).


[Compress, archive and restore trajectories](../docs/running-evals.md#trajectory-storage).
