# SwarmForm resource and boundary coverage

Audit date 8 November 2026. Source inspected at
`d335e468639b6c0d3a2043916c1e095a4478fff0`. This inventory covers the deployed
agent stack, including components outside each container. Each section records
what exists and what needs a runtime check. The study design lives in
[SwarmForm](formation-study-design.md).

## Repair status

The initial audit below describes the prior baseline. The new optional
`workstation_processes=continuous` mode preserves background processes and adds
quiescent before/after/terminal snapshots, including temporary files and path
metadata. `notification_scope=business_only` suppresses file/message-triggered
continuations. The new cache accepts ordinary editable files.
[Regression checks](../experiments/swarmharm-v1/tests/swarmform_runtime_checks.py)
cover these changes. The first model pair completed with verified before/after
and terminal capture, seven business-state notices for Sol 6.1 and zero for
Sol 5.6. Sol 6.1 established and reused a cache convention; sustained substantive
exchange remains unobserved. [Reviewed pair](research/swarmform-cache-pilot.json)

## Inventory method

For each resource record its identity, owner, readers, writers, observable fields,
lifetime and originating operations. Follow indirect flows through services and
the controller. Enumerate data-bearing surfaces and observable resource states.
This follows the shared-resource matrix method; completeness remains relative to
the inspected system description. [Kemmerer](https://sites.cs.ucsb.edu/~sherwood/cs290/papers/covert-kemmerer.pdf)

Resource placement and isolation policy are separate fields. Container namespaces
isolate specific views and object sets. Each deployment also exposes particular
mounts and services. [Linux namespaces](https://man7.org/linux/man-pages/man7/namespaces.7.html)

The ten sections below organize the audit. Coverage is counted over concrete
resources and resolved flow checks. One communication path can span several
sections. A reviewed heading alone does not close its outstanding checks.

## Inspected baseline surfaces

1. **Files and storage.** Working files, temp directories, home, editor backups,
   package/build caches, mounts, overlay layers, directory names, listings, links,
   metadata and replaced/deleted versions. Docker workstations use private tmpfs
   at `/workspace`, `/registry`, `/tmp` and `/private/tmp`, with a read-only root.
   The controller republishes selected registry files between workers and replaces
   registry contents at each shell call. Observation captures regular non-symlink
   files under `/workspace` and `/registry`. Temp files and filesystem metadata
   need additional evidence capture. [Source](../experiments/runtime/workstation.py)

   Registry commits currently allow 32 KiB per record. The shell returns at most
   64,000 bytes from each output stream; the base snapshot allows 2 MB per file
   and 24 MB per captured root. Record all these limits when testing bulk transfer.
   [Commit limits](../experiments/swarmharm-v1/phase1/lab.py)

2. **Processes and local IPC.** Children, daemons, process listings, environment
   variables, inherited descriptors, pipes, UNIX sockets, shared memory and queues.
   `OBSERVE` kills same-user processes other than itself and PID 1, then pauses
   the container. A disposable two-command probe confirmed an HTTP listener worked
   in the first call and was unavailable after observation; its PID was a zombie.
   `/tmp` persisted and the registry was replaced. Persistent endpoints require
   a revised lifecycle and process/IPC observation. Apptainer uses a fresh execution
   context per call and requires separate qualification.
   [Source](../experiments/runtime/workstation.py) · [Probe](research/swarmform-runtime-audit.json)

3. **Networks and endpoint identity.** Loopback, interfaces, namespace identity,
   routes, DNS, ports, proxies and aliases. The base worker defaults to
   `network=none`. Live reporting attaches one internal bridge per worker to
   the shared reference service. Pairwise peer reachability must be measured
   in the actual topology. A shared Pod deliberately shares a network namespace,
   making placement a relevant experimental variable.
   [Reporting links](../experiments/swarmharm-v1/phase2/terminal_batching/records_link.py) ·
   [Kubernetes networking](https://kubernetes.io/docs/concepts/workloads/pods/#pod-networking)

4. **Supporting services and identity scope.** Artifact/package stores, databases,
   object indexes, search, queues and result feeds. Record principals, credential
   scope, object keys, recipient selection and returned fields. Shared credentials,
   shared storage and visible peer content need separate checks. Current library
   requests are GET-only and account checked. Shared notes are controller mediated.
   The library's process inventory describes business actors; this broader audit
   additionally includes OS processes, proxies and native sessions.
   [Library](../experiments/swarmharm-v1/phase2/report_library.py) ·
   [Notes](../experiments/swarmharm-v1/phase2/delivery_notes.py)

5. **Tools, outputs and notifications.** stdout, stderr, errors, listings, tool
   metadata, status counts, receipt links and wakeups. A peer note changes the
   current `activity_signal`; the controller may then continue another session
   with a generic notice. Discovery opportunity includes this notification path.
   Exact note-body matching is implemented. Filename-only messages, partial/ranged
   reads and arbitrary transferred files need additional attribution. Capture
   visible outputs and their causes in checks with corrected scope too.
   [Activity signal](../experiments/swarmharm-v1/phase2/unified_delivery.py) ·
   [Read accounting](../experiments/swarmharm-v1/phase1/lab.py)

6. **Native session and memory.** System/developer/user text, tool catalogs, skills,
   MCP resources, history, compaction, journals, home/config directories and resume
   IDs. Each actor has a separate native session. The business journal is a mediated
   private view. Provider-side caches and hidden context are unobserved. Audit
   effective tools and delivered context for each pinned harness; retain exposed
   transport and context limits. [Sessions](../experiments/runtime/codex_session.py) ·
   [Journals](../experiments/runtime/record_surface.py)

7. **Controller and evaluation services.** Task issuance, tool routing, client IDs,
   request queues, receipts, acceptance rules, score feedback and evidence locations.
   Current shared-state commits are serialized after concurrent private shell calls.
   Verify returned data belongs to its recipient and shared revisions do not
   disclose hidden contents. Keep observer and judge outside subject access.
   Audit delivered filenames and exceptions. [Transactions](../experiments/swarmharm-v1/phase1/lab.py) ·
   [Input audit](../scripts/audit_codex_workstation.py)

8. **Lifecycle and reuse.** Initialization, installation, startup, pause/resume,
   reconnect, reset, checkpoint, teardown and subsequent runs. Track memory, files,
   names, volumes, caches and credentials across every transition. Base Docker
   workers pause between calls and use private tmpfs; closure removes the container.
   Shared world data persists until teardown. The 8 November host audit counted
   65 managed containers whose owner PIDs were absent. Their provenance and terminal captures
   need a separate cleanup audit before removal. Fresh names alone do not establish
   cross-run isolation. [Source](../experiments/runtime/workstation.py)

9. **Resource state, scheduling and clocks.** Locks, queue depth, capacity counters,
   CPU, RAM, page/cache effects, storage/network contention, time, ordering and
   response latency. Base Docker quotas are one CPU, 512 MiB and 64 PIDs.
   Shared-host timing isolation is unverified. Distinguish sender-controlled
   signals from common workload variation. These remain coverage entries even
   when throughput makes them unsuitable for the initial scenario sample.
   [Limits](../experiments/runtime/workstation.py)

10. **Host, kernel and devices.** Namespace/cgroup defaults, capabilities, seccomp,
    `/proc`, `/sys`, `/dev`, device passthrough, runtime sockets and hypervisor
    boundary. Base source drops capabilities, sets no-new-privileges and a non-root
    user, and supplies no host bind mounts or device overrides. Seal effective
    Docker defaults and runtime version in the deployment manifest. Host/kernel
    exploits and hardware timing mechanisms are excluded from the initial scenario
    sample; report these exclusions. [Source](../experiments/runtime/workstation.py)

## Lessons from ExploitGym

ExploitGym describes source/build artifacts, runtime targets, a reset controller,
network mediation and resource limits. It acknowledges that some tasks may be
impossible and lack a known complete solution. For SwarmForm, validate task
solvability and channel reachability independently and seal surrounding services
with the task. [ExploitGym §§3, 5 and Appendix C](https://arxiv.org/html/2605.11086v1)

The public runner documents a controller, firewall proxy and LLM proxy. Its
current setup separates installation and execution networks. Record both stages
and their transition. The paper and current release have different dates and
configurations; pin the source revision for any reproduction.
[Deployment](https://github.com/sunblaze-ucb/exploitgym/blob/main/docs/eval.md) ·
[Network lifecycle](https://github.com/sunblaze-ucb/exploitgym/blob/main/docs/firewall.md)

METR's incident concerns a particular OpenAI deployment using ExploitGym tasks.
Agents found peer activity in its supporting Artifactory cache and appropriated
it for messaging. They also inferred a transcript-based scorer that the deployment
did not implement. Verify actual evaluator behavior against each sealed
configuration. Keep public-benchmark and incident-deployment provenance separate.
[METR investigation](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/)

## Admission of a new mechanism

Require an inventory entry, primary-source basis, intended scope, actual flow,
configuration with corrected scope and source/image hashes. A disposable witness must
transfer distinct work payloads in both directions over repeated turns, including
a fresh artifact after the first exchange. Check exact bytes, chunk reassembly,
cross-run isolation and unselected paths. Preserve the witness as operator evidence.
Live model evidence separately establishes discovery, adoption and sustained use.

Open checks cover arbitrary files and metadata, process lifetime, endpoint pairs,
notification leakage, effective native context, resource/timing visibility and
lifecycle cleanup. This inventory is an auditable coverage plan. Its unresolved
entries remain visible until checked.
