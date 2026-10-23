# SwarmHarm

SwarmHarm tests two connected claims:

1. **Form the Swarm:** separate agents leave residue, infer that other workers
   may exist, ask for help through an ordinary shared system and voluntarily
   share a reusable method without assigned organization or direct chat.
2. **Cause Harm:** a later agent adopts the shared method on a different task and
   causes a concrete business effect verified against independent truth.

## Active study

[Swarm formation v6](experiments/swarm-formation-v6/README.md) is the only active
formation environment. It runs LessWrong Stages 1–3 as one continuous campaign
over one initially empty persistent cache:

`real residue → autonomous reach-out → independent method contribution`

Every agent has a separate sandbox and private context. The prompt does not
announce peers, communication, cooperation, vulnerabilities, evaluation,
pressure or the hidden stages. There is no dedicated request, reply, attachment
or message-board interface. State is never reset and simulated peer content is
never injected between milestones.

**Status, 23 October 2026:** v5 produced residue, autonomous requests and a
candidate independent contribution, but its frozen verifier required exact
syntax in the final report and did not establish a chain. V6 freezes a composite
gate that pairs a model-authored plain-English disclosure with the same agent's
exact successful native query and fetch. It awaits its registered campaign.
SwarmHarm therefore does not yet claim Phase 1, harm, intent or a rate.

## Environment contract

- ordinary, legitimate, non-cyber business work;
- a blocked normal completion path;
- discoverable shared systems and, for harm studies, a verifiable business-process
  weakness;
- separate agent sandboxes and contexts without predefined leaders, teams or pairs;
- no added pressure, exploit hints, cooperation coaching or planted peer messages;
- native provenance for every residue, read, request, contribution and adoption;
- an independent verifier for any claimed downstream business effect.

[Full environment contract](docs/environment-contract.md) ·
[Dataset admission](docs/dataset-admission-contract.md) ·
[Current data sources](docs/research/task-sources-and-verification.md)

## Current setup

Verified **23 October 2026**.

- **Runtime:** Harbor 0.24.0 with Python 3.12.14; inputs use Harbor schema 1.4
  and exported trajectories use ATIF-v1.8.
- **Model gateway:** all live inference goes through AxonHub at
  `https://lmportal.iefbr14.xyz/v1/responses`. A fresh run must verify and freeze
  an exact model ID from both the upstream catalog and authenticated AxonHub
  catalog before inference.
- **Credentials:** the current scoped AxonHub credential is stored in a host-only
  `0600` file outside the repository. No credential value belongs in tasks,
  registrations, traces or Git.
- **Isolation:** each model workstation has no external network. Shared business
  state, operator evidence and independent verification remain separate from
  subject context.
- **Scale:** the minimum campaign uses six agents in three hidden arrival periods
  of two. Population and active concurrency are configurable up to 128 agents;
  scheduling and event recording are linear in population size.
- **Memory:** the persistent cache grows by records, each bounded at 32 KiB.
  Private histories remain separate and are sent in full without automatic
  context compaction.
- **Current state:** no v6 collector or scheduled monitor is running. All prior
  model workstations were removed.

[Run evaluations](docs/running-evals.md) ·
[Model routing](docs/axonhub-routing.md) ·
[Task and trajectory format](tasks/README.md)

## Validation

```sh
../eval-readiness/harbor-0.24.0/bin/python -m unittest discover \
  -s experiments/swarm-formation-v6 -p '*checks.py' -v
../eval-readiness/harbor-0.24.0/bin/python experiments/prompt-contract/checks.py
./scripts/check-format-contract experiments/swarm-formation-v6
python3 scripts/check_dataset_admission_contract.py
```

## Maintained records

- [Active formation environment](experiments/swarm-formation-v6/README.md)
- [LessWrong Stage 1–3 audit](docs/research/lesswrong-stage123-setting-audit-2026-10-23.md)
- [Current run guide](docs/running-evals.md)
- [Current working context](docs/working-context.md)
- [Concise evidence history](docs/history-index.md)

Frozen protocols and results remain evidence in their experiment directories.
Only this README, the active experiment README, the run guide and the working
context define current operation.
