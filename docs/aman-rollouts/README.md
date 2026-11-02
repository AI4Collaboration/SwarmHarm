# Aman's rollout registry

This namespace covers **Aman's own local executions and preparations only**.
Terry's originals keep their names, registrations, evidence, scores and indexes.
Our reproductions reference his condition as provenance; they are separate records.

Start with the [searchable index](index.md). The [JSON registry](registry.json)
contains exact settings, original names, archive locations and evidence digests.
The [guideline audit](guidelines.md) distinguishes this organizational change
from historical execution exceptions.

## IDs

`EXP-004-C02-R01` means experiment 4, intended condition 2, collection attempt 1.
Its readable label is **Communicating score-decay swarm / 10 assignments /
employment pressure / Sol 6.1 high / Pi / four agents**.

| Part | Meaning | Allocation rule |
| --- | --- | --- |
| `EXP-004` | Experiment and research question | Never reuse or renumber |
| `C02` | Intended treatment within that experiment | Never silently change its definition |
| `R01` | Actual collection execution, including failed/preflight-only attempts | Assign once collection starts; never reuse |
| `P01` | Preparation, including rejected launches and failed controls | Separate namespace; not a rollout count |

Every record retains a stable P ID. When collection starts it also receives an
R ID. An uncollected preparation has no R ID. Original date-prefixed names remain
searchable aliases. IDs were assigned retrospectively on 2 November 2026;
they are not represented as original preregistration IDs. Earlier `EXP-007`
examples in chat were illustrative, not allocated records.

R is an execution ordinal, **not a claim of a matched independent repetition**.
Source revisions, model settings, fixtures, tools, route and budgets remain
bound separately. Earlier faulty v1/v2 swarm attempts retain their place in
history and are not pooled with v3 trajectories. A treatment change needs a new
condition. A new model call after a terminal attempt needs a fresh frozen
registration and a new R ID; refreshing this registry authorizes no inference.

## Current experiments

| ID | Scope |
| --- | --- |
| EXP-001 | Financial Claude harness and native goal controls, 28 October |
| EXP-002 | Connected formation/continuation comparisons across four work domains, 29 October |
| EXP-003 | Earlier isolated score-decay sessions, a known setup deviation |
| EXP-004 | Communicating score-decay swarm, including superseded setup attempts |
| EXP-005 | Our uncapped Claude reproductions of Terry's conditions |
| EXP-006 | Our Claude reproductions with the cumulative 25-turn ceiling |

## Update workflow

Maintain the registry and readable index as part of each Aman-owned rollout:

1. At preparation, assign the next unused P ID within the intended condition.
   Record the legacy name, exact settings, original registration and evidence
   location. Keep failed and superseded preparations visible.
2. When collection actually starts, assign the next unused R ID in that condition
   and add it to the same record. A preparation that never starts keeps only P.
3. At termination and review, update status, original evidence/review pointers
   and SHA-256 bindings. Preserve failures, interruptions and original review labels.
4. Update `registry.json` and `index.md` together, review the diff, then commit
   and push the documentation. Never reuse IDs, silently reclassify a condition,
   drop an old record or overwrite a frozen evidence binding.

The JSON registry is the detailed ledger; the Markdown index is its readable
lookup. There is no updater script, collector, scheduler or runtime dependency.
This recordkeeping does not replace the shared preparation, freeze, collection,
review or export pipeline and does not authorize inference.

The inspected archive is `/Users/agokrani/Documents/git/eval-readiness`.
Review copies, prepared evidence snapshots and offline diagnostic fixtures are
excluded from rollout counts. Coverage is this local archive, not every machine
or every project. Review ownership explicitly before adding another archive.

## Evidence limits

Registration and frozen source fingerprints identify exact configurations.
Where available, the registry links byte-identical registration additions in
local Git and a source commit reported by the historical review. An unresolved
Git binding remains explicitly unresolved; it is not guessed.

`reported_review` copies historical flags, without regrading them or promoting
a mechanical pass into knowing coordination or a harm claim. Raw evidence and
full reviews remain outside Git. Negative-result lessons stay in the root
README's Takeaways. Collection status, task completion, accepted publication and
business effects remain distinct. Provider holds and budget cutoffs retain
their original labels. There are no aggregated success rates in this registry.
