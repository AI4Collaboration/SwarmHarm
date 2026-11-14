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

Use Python 3.12, Node.js 22.19+, Git and Docker with Linux containers. The full matrix requires ARM64 Linux or ARM64 container emulation for the pinned jq task. Build its reference locally once. Workstations run separately from the model endpoint. Only the operator process receives the API credential.

```sh
# From repository root
bash scripts/setup-local all
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r rollouts/requirements.txt
docker build --platform linux/arm64 -t swarmform-workstation \
  -f shared/Dockerfile.workstation shared
export SWARMHARM_DOCKER_IMAGE="$(docker image inspect swarmform-workstation --format '{{.Id}}')"
bash rollouts/build-jq

export OPENAI_BASE_URL=http://localhost:8000/v1
export MODEL=openai/gpt-6.1-sol       # selected model identity; see the lineup
# Set OPENAI_API_KEY or OPENAI_API_KEY_FILE if your server requires authentication.
python rollouts/run_matrix.py --model "$MODEL" --populations 4 8 16
python rollouts/run_matrix.py --model "$MODEL" --populations 4 8 16 --execute --out ../swarmform-runs
```

The first command after API setup prints 72 planned cohorts without contacting the endpoint. The second runs them sequentially. Participants within each cohort work concurrently. Both runners select Codex for OpenAI, Claude Code for Claude and Pi for the other listed families. The endpoint must support Chat Completions function tools, tool results, and `usage.total_tokens`. A host-side adapter preserves each native session; only our own testing uses AxonHub. Start with the [N=4 model integration check](../docs/model-lineup.md#one-endpoint-one-key). Use `--served-model` for a different provider spelling of the same model, or `--api-protocol native` for a gateway exposing Responses/Messages directly. The previous plain Chat Completions loop is explicitly selectable with `--harness chat-completions`; it is a different harness condition. Use `--revision` to record the deployed checkpoint. Each cohort has an aggregate allowance of N CPU cores and N × 512 MiB memory: separate per-agent containers in unintended conditions, an equivalent shared-container allowance in the intended condition. Record host capacity when comparing timings. Each group has at most 600 seconds from participant activation, 32 responses, 96 tool calls and 500,000 observed tokens per agent. Tokens include input and output on every response. The token stop is applied when the server reports usage. A final response ends that agent’s work. The cohort stops when all agents finish or on the first exhausted group boundary or participant error. Setup, capture and cleanup occupy additional wall time.

**Collection order.** Start with one task at N=4, inspect the captured records and disk use, then run the full 4/8/16 plan. Each size has 24 cohorts, giving **72 cohorts / 672 agent trajectories per model and repeat**. Keep task, communication condition, model revision and budgets fixed when comparing populations. `--repeats` adds fresh cohort directories. Repeats use the same task instances, so they measure rollout variation on these tasks.

The default account names are numbered. The original N=3 `--names physicists` treatment remains available for its counterbalanced Oppenheimer/Bethe/Bacher identities. It is not required for scaling.

The matrix writes `plan.json`, a live `index.json`, per-cohort logs and separate directories outside Git. Running the same plan again skips completed cohorts and reports incomplete directories. To register a fresh attempt at a failed cell, use a fresh output root. For a **single configuration**, run the following from the repository root.

```sh
(cd rollouts && python -m swarmform run --model "$MODEL" --task decoder-release \
  --population 4 --channel direct --out ../../decoder-release-direct)
```

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
