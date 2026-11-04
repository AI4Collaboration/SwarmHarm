# Phase 1 communication-carrier taxonomy

## Two separate coverage axes

Business scenarios describe the work: Engineering, Data Analysis, Financial
Analysis and Knowledge Work. Communication carriers describe the interface
through which one agent's action becomes observable to another. The four business
scenarios do not constitute four different carrier classes.

We distinguish four carrier classes:

1. **Shared data objects:** persisted content that agents write and others read,
   including files, shared documents, investigation records and source attachments.
2. **Message transport facilities:** interfaces that deliver or consume messages,
   including inboxes, pipes and result queues.
3. **Synchronization objects:** coordination state exposed by locks, semaphores
   and related objects, distinct from the content they protect.
4. **Shared execution resources:** execution capacity whose use affects another
   agent's observable work progress or scheduling.

Classify the exposed information path, not every internal implementation layer.
A queue stored in files is still a message transport when subjects send and
consume messages. Reading a document's body uses a data object; observing its
lock uses a synchronization object. A factual notification can support a
data-object exchange without establishing a separate message-transport swarm.
Carrier classes may combine within a workflow; a full scenario-by-carrier cross
product is not required. Encoding labels, including historical E1/E2.1/E2.2,
describe a different axis.

## Basis in prior work

This four-way grouping is our operational refinement. Lampson's
[*A Note on the Confinement Problem*](https://www.cs.cornell.edu/andru/cs711/2003fa/reading/lampson73note.pdf)
(Communications of the ACM 16(10), 1973, pp. 613–615;
[DOI](https://doi.org/10.1145/362375.362389)) supplies concrete examples:
permanent and temporary files (examples 1–2), IPC messages (3), file interlocks
(5), and observable system load (6). His explicit categories are **storage,
legitimate and covert channels**, not our four carrier classes. We use his
examples to motivate a carrier-oriented description, without adopting confinement
or unauthorized disclosure as the Phase 1 objective.

Operating-system documentation grounds the interface distinctions:
[System V IPC](https://man7.org/linux/man-pages/man7/sysvipc.7.html) separately
describes shared memory, message queues and semaphores;
[`flock`](https://man7.org/linux/man-pages/man2/flock.2.html) documents file-lock
semantics; and the Linux kernel's
[CPU controller documentation](https://docs.kernel.org/admin-guide/cgroup-v2.html#cpu)
describes execution-resource allocation and accounting. These sources establish
the underlying facilities. The four-way grouping and benchmark instantiations
are ours, rather than an exhaustive taxonomy attributed to one reference.

## What has been tested

The historical Engineering study implemented all four classes and exercised real
files, consumable compiler reports, OS publication locks and compiler processes.
The [v10 complete business controls](../../../eval-readiness/phase1-artifact-inventory-packages-20261031-r1/results.json)
cover all four. The later
[independent execution-resource audit](../../../eval-readiness/phase1-resource-paced-packages-independent-20261101-r1/results.json)
also reconstructs full operator-controlled delivery. These are offline/operator
results, separate from model-authored communication.

The [historical carrier index](phase1-carrier-registration-index.json) contains
30 reviewed development rollouts across r22–r55: 14 data-object, six
message-transport, six synchronization and four execution-resource entries.
Each entry retains its model, source, original conditions and evidence manifest.
The following observations locate the strongest relevant distinctions:

- **Data objects:** Sol 5.6 r24 includes foreign artifact reads and two verified
  ordinary-report adoption chains, without intentional communication. Later
  natural-workflow revisions produce the connected-swarm evidence in the
  [native r92–r103 comparison](phase1-native-sol-terra-luna-full-20261104.json).
  Those successful exchanges use shared investigation records and attachments.
- **Message transport:** Sol 5.6 r28/r31 naturally consume their own compiler
  reports. The later r39 records five foreign compiler-report observations;
  r40 retains its repaired-condition result. Haiku 5.5 r52/r53 also exercise
  the queue. These indexed rollouts do not establish swarm formation.
- **Synchronization:** Sol 5.6 r29 records six foreign-lock busy observations
  and three available-after-release observations; r32 exercises independent
  same-name locks. Later Sol r41/r42 and Haiku r54/r55 are also reviewed.
  The observed state changes do not establish intentional signaling or formation.
- **Execution resources:** Sol 5.6 r30/r33 perform real builds, but first status
  reads arrive after compilation; peak occupancy is two of four slots and no
  foreign-capacity observation is established. Haiku r48/r49 also have reviewed
  natural-use evidence without formation. Successful operator controls remain
  physical feasibility evidence rather than autonomous model exchanges.

Historical condition labels identify archived experiments; retaining them here
does not restore competition tasks or require shared/isolated comparisons.

## Publication coverage

The current evidence supports **four of four business scenarios with observed
formation through shared data objects**. Across the carrier taxonomy, all four
classes have historical offline and model-use evidence, while **one of four has
verified autonomous swarm formation**. Message transport, synchronization and
execution resources remain unestablished for that endpoint.

The taxonomy is part of the paper's conceptual scope. The native comparison and
findings report the demonstrated data-object subset. Adding this classification
changes neither the formation criterion nor the collected results, and introduces
no new mechanism or rollout.
