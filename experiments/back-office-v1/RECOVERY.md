# Durable back-office runs

24 October 2026: export and verify the parent launch directory as well as its
individual campaign directories. Per-campaign copies alone omit parent
registrations, completion records and launcher logs. `verify` accepts a parent
with immediate campaign recovery indexes, checks all their expected episodes,
and hashes the whole parent tree. Unknown requests still block clearance;
clearance never authorizes a shutdown. Historical raw trees remain frozen.

23 October 2026. This revision passed offline and local Docker/Harbor integration checks. It is not
installed on existing EC2 instances, and does not change active research runs.
Historical tasks and artifacts remain frozen. Never edit their verifier in place.

## Before a separately authorized future run

Emit to a NEW directory with `emit_harbor.py`; the runner rejects an older grader
or verifier wrapper. Preserve the old task snapshot for historical comparisons.
Run `python3 test_durability.py -v` from this directory.
The integration suite passed 240 local scripted controls and 19 prompt-contract
checks; these are mechanics checks, not new model behavior results.
A live OpenRouter preflight returned HTTP 401 and no episodes were dispatched.

`run_model.py` requires `--out NEW_RUN_DIR --backup-dir NEW_BACKUP_DIR
--instance-id INSTANCE_OR_HOST`, alongside explicit tasks/model and the approved
run settings. Both directories must be new and disjoint. No credentials are saved.
Only an existing host environment supplies the API credential; setup here creates
no credentials, resources or spending authorization. The recovered runtime's
reasoning and timeout options are retained. Actual served model/provider IDs stay
in each native response and episode metadata.

Before dispatch, the runner writes the full expected episode list, host, supplied
instance identity, source revision and dirty diff, settings, backup location and
recovery instructions to `recovery-index.json`. Each episode freezes the exact
input files, runner source, grader hash and immutable Docker image identity.
Builds and execution use the copied task, not a subsequently edited source tree.
Do not point this private output at a public/shared directory: native responses,
reasoning, instructions and operator-side truth belong in restricted storage.

## During collection

Each request is journaled with a locally generated ID before transmission.
The raw response is fsynced before JSON parsing, retaining provider response IDs
and request headers when supplied. Tool preparation, raw assistant messages,
metadata and tool results are journaled immediately; transcript snapshots use
atomic rename and fsync. Root-owned business evidence is copied between commands.
A host crash during a command may leave its result unknown; recover the retained
container and audit before taking any further action.

There are no automatic retries, including timeouts, rate limits or server errors.
Ambiguous requests remain unresolved, and hold new turns in this campaign. Requests
already in flight are allowed to return. Reconcile saved responses and provider
request IDs before any manually authorized continuation. A prepared request with
no response is conservatively unknown even if it may never have reached the API.
Do not silently resend it or declare its cost zero. This runner has no auto-resume.

Each completed episode is copied to the backup directory and hash verified before
its own completed container is removed. A collection or export exception preserves
the container identity and `recovery_required` status. No process-wide kill, EC2
shutdown, credential change, budget lock change or control of other owners is used.

## Grading and regrades

Malformed list/dictionary item IDs are outside the wave scope; rejected requests
remain in the audit. A missing audit/state/truth or scorer exception is a
`grading_error`. The verifier omits invalid reward files and emits a separate
`grading-status.json`, and fails its process rather than inventing a numeric
behavioral score. Native metadata/summary use null behavioral metrics on invalid
grades or API errors. A valid final-state grade on a turn-capped episode does not
make that episode complete; `episode_complete` records that distinction.

Harbor 0.24.0 incorrectly summarizes an empty reward object as a completed trial
with mean zero. Invalid reward files must therefore be absent, so Harbor reports
a missing-reward infrastructure error. Native consumers use grading-status.json.
The native runner requires this new status contract and rejects stale emitted tasks.

For a historical regrade, run `python3 regrade.py EPISODE_DIR TRUTH_JSON NEW_DIR`.
This copies the original verifier/meta unchanged, records the original artifact
hashes, new grader/truth hashes, and writes a separate `regrade.json`. API errors
remain unscored; crashes produce null scores. It never dispatches a model/service.

## Export and authorized shutdown gate

After collection (or while recovering a stopped collector), use:

```sh
python3 durability.py export RUN_DIR LOCAL_EXPORT_DIR
python3 durability.py verify RUN_DIR LOCAL_EXPORT_DIR
```

Run `verify` on a machine able to read BOTH copies. It checks every expected
collection, unresolved request records, every source/destination file hash, and
the saved export manifest. A pending episode, torn journal, missing metadata,
unknown request, missing file or corrupted copy prevents clearance. The runner
also performs a final export and returns failure if clearance fails.

Clearance proves collection/export, not that all experiments passed or all episodes
reached a final answer. Keep incomplete episodes and grading errors in reports.
This command never grants shutdown permission or shuts anything down. Obtain the
specific target/action approval separately and preserve other owners' processes.
No universal cloud stop hook has been installed; operators must use this gate
before any separately authorized shutdown. On a remote collector the first backup
may be a mounted separate volume; then export and verify on the Mac as well.
Two directories on one disk do not protect against loss of that disk or machine.

## Cloud backup

A versioned off-machine destination is still required. No bucket/account/prefix
was supplied, so no upload, new storage resource, credentials or cloud spend was
created. Use an approved private destination with version history, preserve the
file manifest and immutable object/version receipts, and verify a downloaded
copy before labeling that backup verified. Do not put API credentials in archives.
Until that destination is configured and checked, report cloud backup as pending.
