# Reproducing the Engineering carrier evidence

## Scope and units

Current work follows the four natural business scenarios in the
[scenario inventory](phase1-publication-units.md). Historical carrier packages
below reproduce original results only; they do not define current experimental
conditions or pending work.

## Historical verified package

`../eval-readiness/phase1-engineering-offline-repair-evidence-20261103-r1`
contains r22–r42 and 15 audit roots. Verification from `/tmp` with Python 3.9
passed 33,011 package-file hashes, all 21 rollout reconstructions and 18 operator
worlds, without network or model calls. The explicit v12 offline evaluator has
150 hash-bound files. The portability audit is
`../eval-readiness/phase1-offline-repairs-portability-audit-20261103-r1/manifest.json`.
This package preserves the reviewed historical evidence; it does not contain a
v12 model rollout or establish current-source live validation.

## Historical Claude Code supplement

The separately verified `../eval-readiness/phase1-cc-portability-20261103-r1/package`
adds fully reviewed r47, with 6,508 hash-bound files. Its offline verification
from `/tmp` passes physical, package, pressure and native semantic reconstruction
using the included 152-file evaluator. The original historical package above
remains unchanged. No provider HTTP context, independent human judgment or
new model execution is claimed by this portable check. Final consolidation uses the current atomic-input evaluator and all current
condition reviews; see the catalog for its status.

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
communication endpoints using the explicit frozen evaluator named in `mapping.json`, when supplied,
or the latest included rollout validator. Both retain historical revision
support. The explicit evaluator is separately hash-bound and may postdate
the subjects; it is offline reinterpretation, not matching-source live evidence. It also reconstructs recorded CPU intervention results and
included operator-control worlds. A failure exits without changing the original
evidence. `mapping.json` maps original absolute provenance paths to portable
locations; original records are not rewritten.

The consolidated verifier also reconstructs every Claude SDK response and exact
tool return, even when no communication signal is annotated. It rejects extra
unprojected assistant messages, missing or changed tool returns, and delivery
outside the corresponding response interval. For atomic-input registrations it
rechecks the whole initial delegation and every later input before each response.
Legacy v1 registrations retain their startup-ordering limitation; replay does not
retroactively give them atomic delivery. The performance cache reuses only the
JSON decoding of identical terminal-manifest bytes. Every referenced native file
is still read and checked against its original hash; cache or manifest mutation
aborts verification.

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
`--scenario engineering-capacity`, `--harness claude-code`,
`--model-id anthropic/claude-haiku-5.5`, `--model-alias haiku55`,
`--reasoning-effort high`, `--population 4` and `--goal-mode off`.
Use the AxonHub key through the common entry; all model traffic stays on AxonHub.
Historical Pi/Sol runs keep their own settings and are not relabeled as CC.
Engineering installs its ordinary shared-record workflow automatically. Preserve
every prepared input and the actual catalog checks.
Commit and push the registration, confirm a clean matching local/remote source
and all source/input/task seals, then launch that registration once. Do not use
an expired business deadline. Retain all native records and negative outcomes.

The ordinary offline business control is scripts/audit_phase1_cases.py. It checks
actual source-backed delivery through shared records, without a paired exposure
or competition schedule. Operator checks are not model communication evidence.

## Interpretation

Each new revision requires its own matching-source trace review. A successful
Phase 1 result needs intentional sending, exact reads, linked replies, read-back
and group formation. Historical negatives and natural-use results remain valid
observations, but do not finish the user's refinement goal. AI review and
independent programmatic reconstruction are used; no human-rating gate applies.
