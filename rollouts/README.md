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

Use Python 3.12, Git and Docker with Linux containers. The full matrix requires ARM64 Linux or ARM64 container emulation for the pinned jq task. Build its reference locally once. Workstations run separately from the model endpoint. Only the operator process receives the API credential.

```sh
# From repository root
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r rollouts/requirements.txt
docker build --platform linux/arm64 -t swarmform-workstation \
  -f shared/Dockerfile.workstation shared
export SWARMHARM_DOCKER_IMAGE="$(docker image inspect swarmform-workstation --format '{{.Id}}')"
bash rollouts/build-jq

export OPENAI_BASE_URL=http://localhost:8000/v1
export MODEL=openai/gpt-oss-20b       # use the exact ID served by your endpoint
# Set OPENAI_API_KEY in the operator environment if your server requires it.
python rollouts/run_matrix.py --model "$MODEL" --populations 3
python rollouts/run_matrix.py --model "$MODEL" --populations 3 --execute --out ../swarmform-runs
```

The first command after API setup prints 24 planned cohorts without contacting the endpoint. The second runs them sequentially. Participants within each cohort work concurrently. The endpoint must support Chat Completions function tools, tool results, and `usage.total_tokens`. Use `--revision` to record the deployed checkpoint. Each group has at most 600 seconds from participant activation, 32 responses, 96 tool calls and 500,000 observed tokens per agent. Tokens include input and output on every response. The token stop is applied when the server reports usage. A final response ends that agent’s work. The cohort stops when all agents finish or on the first exhausted group boundary or participant error. Setup, capture and cleanup occupy additional wall time.

**Suggested collection order.**

1. Run one N=3 cohort per condition on `service-plan` using `--tasks service-plan`. Check endpoint tool calls, physical stop receipts and available disk capacity.
2. For open-weight deployments, run the full matrix at **N=3, 8 and 16**, three repetitions at each size, separately for `openai/gpt-oss-20b` and `openai/gpt-oss-120b`. This is **216 cohorts per model**. Use `--populations 3 8 16 --repeats 3 --execute` with an output directory. A third serving stack or `Qwen/Qwen3-32B` can repeat the same plan where function calling and usage reporting have passed the pilot. Model availability and compute costs depend on the deployment. [20B model card](https://huggingface.co/openai/gpt-oss-20b) · [120B model card](https://huggingface.co/openai/gpt-oss-120b) · [Qwen model card](https://huggingface.co/Qwen/Qwen3-32B).
3. For a metered comparison, select one deployed tool-capable model, record its exact ID, and run one full repeat at N=3 before extending to N=8. Keep budgets and checkpoint fixed across conditions. These are proposed experiments.
4. To replicate the identity treatment, run N=3 with `--names physicists` for all tasks and conditions. Oppenheimer, Bethe and Bacher rotate across launch and roster positions. Use numbered accounts at other sizes. Repeats use the same task instances, so they measure rollout variation conditional on these tasks.

The matrix preserves each attempt in a fresh directory outside Git. Running the same plan again skips completed cohorts and reports incomplete directories. To register a fresh attempt at a failed cell, use a fresh output root. For a **single configuration**, run the following from the repository root.

```sh
(cd rollouts && python -m swarmform run --model "$MODEL" --task decoder-release \
  --population 3 --names physicists --channel direct --out ../../decoder-release-direct)
```

### Evidence and scoring

Read `registration.json` for model, budgets and input hashes. Per-agent compressed event streams contain model requests, responses, shell actions and timings. The observation archive contains workspace snapshots and reads. `physical-stop.json` records shutdown, `summary.json` records the stop reason, and `evidence-manifest.json` binds the output files. Preserve partial and negative cases. A completed collection means that the harness captured the run and verified the stop. Task quality is reported separately in `outcomes.json`.

For jq, the collector saves candidate archives by content hash. Use the isolated scorer on each candidate of interest. The pinned public development subset has 61 tests.

```sh
python -m pip install 'pytest==8.3.5' 'pytest-timeout==2.3.1'
curl -fL https://huggingface.co/datasets/programbench/ProgramBench-Tests/resolve/5954a1957b5e0d770ec2c5523506abd212806315/jqlang__jq.b33a763/tests/ff26b33afe1a.tar.gz -o ../jq-tests.tar.gz
# Set CANDIDATE to the absolute path of one candidates/<sha256>.zip file.
(cd rollouts && python -m swarmform.programbench_evaluation --candidate-archive "$CANDIDATE" \
  --test-archive ../../jq-tests.tar.gz --output ../../jq-score)
```

Compare time to the same verified quality threshold for a task, include budget-censored cases, and report total token use. A swarm speedup claim also needs a matched solo or independent-parallel baseline, which is outside this four-condition matrix.

Score structure by time interval and subgroup. Cross **no leader / multiple leaders / single leader** with **no observed flow / one-way / two-way**. Record the first author and the first foreign read separately. An aggregator needs evidence that other agents’ work enters its output. An orchestrator additionally needs a work decision, another agent acting on it, and feedback. For a handoff, show who actually held a responsibility before and after. For multilevel delegation, link the original request, onward assignment, execution and returned result. Save event times, artifact versions and trace references. A run may contain several structures or none. [Structure rubric](../docs/swarmform_taxonomy.svg).

