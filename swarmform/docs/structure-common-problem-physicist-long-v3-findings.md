# Navier–Stokes long-v3 with physicist names

Both rollouts closed naturally on 16 November 2026. All 16 native sessions and
ATIF trajectories passed coverage and continuity checks. All eight terminal
views of the shared report agreed within each rollout.

| Condition | Active time | Native responses | Recognized JSON message writes | Observed organization |
| --- | --- | ---: | ---: | --- |
| Shared folder only | 26m 23s | 176 | 0 | Several agents integrated each other's drafts. Faraday performed the terminal synthesis. |
| Team prompt and messaging | 17m 43s | 267 | 211 | Oppenheimer proposed a division of work. Peers adopted it, with Faraday taking lead editing and Feynman auditing. |

In the shared-folder run, Maxwell read and consolidated a Noether manuscript.
Noether then read Maxwell's consolidation and published a revision. Curie also
reviewed and updated the shared report. Faraday incorporated earlier material
from Noether, Maxwell and Rabi and wrote the terminal version. The final writer
alone does not establish an accepted coordinating role.

In the team run, Oppenheimer proposed Faraday as lead editor (messages m0005
and m0009). Rabi, Feynman and Noether explicitly accepted changes in coverage
(m0012, m0014 and m0015). Faraday accepted lead editing (m0016), requested an
audit from Feynman (m0049), and wrote the integrated draft. Feynman read it and
asked Faraday to specify the support and center of a cutoff function (m0181).
Faraday received that correction and applied it, preserving an earlier version
and reporting the revision (m0194). The final report credits the whole group and
identifies Faraday as lead editor. Rabi occupied Research01's former slot.

Both reports describe partial mathematical results and explicitly leave the
arbitrary-data regularity problem open. The operator review verified the
coordination and terminal files. It did not independently adjudicate the
mathematical proofs or all potential delegation chains.

The pair followed [Terry’s original long-v3 design](structure-common-problem-long-v3-findings.json).
Both rollouts used GPT-6.1 Sol high through native Codex and AxonHub, goal mode
off, eight isolated sessions in parallel, and a 90-minute active limit. The
shared-folder rollout ran first. Both used the same name mapping.
The actor's environment file labels its own name. The provided messaging
interface in the team condition uses the new names as addresses. No biographies
or roles are supplied. [Frozen rollout source and registrations](https://github.com/AI4Collaboration/SwarmHarm/tree/fbdda3dd76ece4cdc449496fda251cf71181fc04/experiments/structure/registrations).

| Original label | New name |
| --- | --- |
| Research01 | Rabi |
| Research02 | Feynman |
| Research03 | Oppenheimer |
| Research04 | Curie |
| Research05 | Faraday |
| Research06 | Maxwell |
| Research07 | Noether |
| Research08 | Fermi |

Original actor order is preserved. Compare observed editing, work requests,
actual adoption and feedback with the original findings. A single renamed pair
can show what happened in those runs. Attribution to individual names would
require further comparisons with varied mappings and repeated conditions.

The workstation image is rebuilt from the frozen recipe and the native Codex
version is pinned to 0.166.0. The registration records actual local image,
binary and host identities.

[Private evidence archives and checksums](https://github.com/AI4Collaboration/SwarmHarm/releases/tag/aman-long-v3-physicist-names-terry-format-20261117).

[Structured findings](structure-common-problem-physicist-long-v3-findings.json) · [Rollout status](structure-common-problem-physicist-long-v3-status.json) · [Verified release assets](structure-common-problem-physicist-long-v3-publication.json).
