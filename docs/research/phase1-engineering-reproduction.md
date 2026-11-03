# Reproducing the Engineering carrier evidence

## Scope and units

This release studies one business scenario (`engineering-capacity`), four
concrete carriers and two isolation scopes for each carrier. The maintained
catalog also lists three other business scenarios; they are outside this
revision's implementation and live-validation scope. Executions and subjects
are not additional scenarios.

The release report is [phase1-engineering-publication-report.md](phase1-engineering-publication-report.md).
The machine-readable inventory is [phase1-publication-catalog.json](phase1-publication-catalog.json),
with individual executions in [phase1-carrier-registration-index.json](phase1-carrier-registration-index.json).
Original legacy cache registrations retain their separate index.

## Offline verification

The portable release contains `verify.py`, `manifest.json`, `mapping.json`,
`rollouts/` and `audits/`. Use Python 3.9 or later; the verified offline path uses
the standard library and the frozen code included in the package. It requires
no credentials, model calls, Docker service or access to the original directory.
From any working directory, run:

```sh
python3 /absolute/path/to/evidence/verify.py --replay > /absolute/path/to/replay-result.json
```

Keep the output outside the sealed evidence directory. The command verifies
all package hashes, original terminal manifests and review bindings. It then
reconstructs carrier provenance, actual package acceptance and native annotated
communication endpoints using the latest included validator with historical
revision support. It also reconstructs recorded CPU intervention results and
included operator-control worlds. A failure exits without changing the original
evidence. `mapping.json` maps original absolute provenance paths to portable
locations; original records are not rewritten.

This offline verifier does not rerun a model or recreate historical process
timing. It reconstructs the recorded processes and acceptance rules. Separate
original independent audits also recompiled the delivered source. Repeating
bytecode-digest checks requires the original pinned Python version because
marshalled code is version-dependent; those hashes are not language-independent
binary reproducibility claims.

Each rollout retains its registration, prepared inputs, frozen code, native
sessions and request/response records, world events, compiler-service snapshot,
cleanup evidence, original collection manifest and sealed review sidecars.
Public native text and tool returns were fully reviewed. Encrypted model
reasoning is neither decoded nor interpreted. The manifest authenticates bytes;
it is not a substitute for the declared AI semantic review. Review annotations
and their limits remain visible.

Programmatic checks distinguish completed filings, candidate packages and final
packages. Historical v8 records predate the candidate endpoint and are checked
against their original endpoints. The frozen v11 combined report lacks the
package aggregate; sealed terminal audits and independent portable replay
supply that aggregate without altering the original report.

## Repeating an experiment

A fresh model rollout is a new experiment, not deterministic replay. Use the
common `experiments/swarmharm-v1/run.py` preparation entry and `launch.py`
collector with a fresh output and registration. Select `--study-mode phase1`,
`--scenario engineering-capacity`, `--harness pi-sdk`,
`--model-id openai/gpt-5.6-sol`, `--model-alias sol56`,
`--reasoning-effort high`, `--population 4` and `--goal-mode off`.
The carrier and its repair scope are selected separately from pressure and
renewal basis. Preserve every prepared input and the actual catalog checks.
Commit and push the registration, confirm a clean matching local/remote source
and all source/input/task seals, then launch that registration once. Do not use
an expired business deadline. Retain all native records and negative outcomes.

Physical controls require the real compiler service and isolated workstations.
Their external operator policies supply their own schedules and must never be
included in model inputs. A successful operator control demonstrates an
implementation path, not autonomous discovery, model timing or communication.
The release includes the control evidence and its independent reconstruction
rather than claiming deterministic model behavior.

## Interpretation

One selected execution per restored carrier/scope condition validates that
condition's observed behavior. It does not estimate success rates, establish
randomized pressure effects or imply that unobserved communication is impossible.
Published distinctions are natural business use, foreign exposure, exact source
adoption, intentional sending, replies and recurrent formation. The review
method is AI review plus independent programmatic reconstruction; no independent
human ratings are claimed or required. A complete negative finding can be ready
for publication while the corresponding formation endpoint remains false.
