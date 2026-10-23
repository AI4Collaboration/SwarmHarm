# Harbor task and trajectory contract

The active formation environment is
[swarm-formation-v10](../experiments/swarm-formation-v10/README.md). It generates
one Harbor task package per agent and executes those packages through the
registered campaign adapter so separate sandboxes run concurrently over one
persistent business system.

## Required formats

- **Input:** Harbor task schema 1.4.
- **Runtime:** pinned Harbor 0.24.0 with the execution mode recorded explicitly.
- **Output:** one validated ATIF-v1.8 trajectory per agent plus the native request,
  response and tool records used to create it.
- **Campaign evidence:** a frozen manifest linking agent identity, execution time,
  shared-artifact authorship, reads, contributions and independent review.

A valid Harbor package does not prove native Harbor scheduling. An ATIF export
does not prove input format, correct execution, transfer, harm or intent. Record
each claim separately in `format-contract.json`.

## Package layout

```text
tasks/<task-id>/
  instruction.md
  task.toml
  environment/Dockerfile
  tests/test.sh
  solution/solve.sh
  provenance.json
```

- `instruction.md` is the exact natural business request.
- `task.toml` records Harbor configuration, resources and timeouts.
- `environment/` contains the synthetic business workstation without operator
  credentials or independent truth.
- `tests/test.sh` writes Harbor verifier output.
- `solution/solve.sh` is an optional operator reference, never subject input.
- `provenance.json` records source revision, hashes and adaptations.

## Evidence rules

Keep model scheduling, shared-state timing, budgets and route identity in the
campaign registration. Preserve failed or incomplete calls without inventing
responses. Verify business outcomes against records outside subject control.
Reading shared data alone is not method transfer or harm.

Before inference, validate packages with pinned Harbor, build the environment,
exercise the verifier, audit the assembled subject input, freeze every hash and
push the registration.

[Run guide](../docs/running-evals.md) ·
[Environment contract](../docs/environment-contract.md) ·
[Harbor task documentation](https://github.com/harbor-framework/docs/blob/main/guides/creating-tasks.mdx)
