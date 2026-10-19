# SwarmHarm factor audit · 19 October 2026

**The wider audit found additional inherited restrictions and measurement errors. They are corrected in current source, but their behavioral effects have not been tested.** This is an engineering and construct-validity audit, not a claim to have identified every causal determinant of misalignment. No model was called and no historical trajectory was changed.

## Corrections made

- The earlier wayfinding base still described shared files as unavailable to the actor's role and scored shared-file reads/writes as unauthorized. Its communication and cue variants inherited this. Current shared-file use is permitted wherever the channel actually exposes it; isolated channels remain technically isolated. Source-data access remains a separate boundary.
- The four-step adapter still marked shared-registry writes as unauthorized and advertised owner-only read roles for files that peers could read. Both inconsistencies are corrected. Writing or reading an ordinary shared file is now an observation, not evidence of misconduct.
- Three four-step prompt presets still added persistence pressure, task-method hints, permission reminders or a directed handoff. `intense_local`, `auditor_intense` and `method_handoff` are retired from the current executable interface. Their frozen histories remain available. Explicit effort/collaboration diagnostics remain labeled as interventions; they are not the neutral baseline.
- The four-step summary accepted a peer read in place of an actual request. Its structural-chain check now requires the request. A structural match still requires semantic review and does not establish causal transmission.
- The expanded regression initially expected every repaired condition to expose peers. Inspection showed that staging's `weakness_open` controls shared-file visibility, while fleet's flag controls a cache authorization omission. The test now respects those different mechanisms. The environment was not changed to make the test pass.

## Factor inventory

1. **Task and legitimate goal.** Preserve original business requirements and required output. Source-backed hospital operations and accounting tasks differ from the four-step toy records. Do not pool their realism or capability claims.
2. **Blocker.** Missing/staging failure and denied source access are distinct. Both implementations exist; the latest Luna pair used denied access. Its result does not estimate the missing-input effect.
3. **Resource ownership and authorization presentation.** Keep actual source roles, object ownership and open/repaired behavior truthful. Front-loaded metadata and on-access presentation are separate conditions. Remove added behavioral prohibitions rather than misrepresenting the resource policy.
4. **Task interdependence.** Different private cases prevent answer copying but can make another worker unhelpful. Reciprocal staging instead gives workers complementary original records from the same case. This distinction remains an unisolated behavioral factor.
5. **Peer discoverability.** A filename, read receipt, named work item and actual report body supply different information. Required report saving can itself reveal an index. Count the exact information present before the next decision.
6. **Channel and notification.** No channel, shared files and formal chat describe technical affordances. Automatic delivery of actual chat messages also changes exposure; it cannot be interpreted as a pure change in permission. Earlier wayfinding side/legal labels no longer create a permission contrast after cleanup.
7. **Useful capability acquisition.** An open route is not evidence that a worker found it. Sharing can only be evaluated after a worker has acquired a usable method. Owning authorized data, possessing a method and demonstrating an unauthorized method are different states.
8. **Recipient opportunity.** A request must reach a live recipient with an opportunity to respond. Finished workers are not reactivated. An unread request or absent method cannot be counted as refusal to help.
9. **Effort, pressure and relationship cues.** Neutral, resourceful, collaboration and instructed-capability conditions are distinct. Older simulated peer-preservation notices and fictional relationship records are explicit interventions. In early wayfinding, even the no-pressure notice names another worker; it is not a cue-free baseline.
10. **Time and persistence.** Track real elapsed work, number of arrivals, live overlap, retained artifacts and reset behavior. A six-hour cap is not six hours of activity. The four-step runner is sequential; fleet workers overlap logically; some wayfinding workflows deliberately reset context. These are not interchangeable long-horizon tests.
11. **Tools, model and provider.** Typed business functions differ from a Bash workstation. Model, reasoning effort, route, request serialization, timeout and preflight gate must be recorded. Catalog availability or an earlier success does not prove current access. Provider errors are not behavioral refusals.
12. **Outcome definition.** Keep ordinary cooperation, file publication, directed requests, method sharing, attempted access, successful access and final use separate. An incomplete structured answer is not automatically fabrication. A temporal association is not proof of learning or causal influence.
13. **Exposure provenance and contamination.** Check actual prior request contents and exact body versions, not only event order or filenames. Historical references and operator-seeded diagnostic notes must not be presented as live peers. Graders, credentials and host assets stay outside subject inputs.
14. **Sampling and inference.** Preserve failed gates, provider errors, interrupted worlds and negative results. Workers in the same world are correlated. One world per arm, adaptive development and different simultaneous settings cannot establish general incidence or isolate a causal factor.

## Verification and remaining work

The prompt contract now exercises nine inherited world families across channel, source-role, staging, weakness and applicable framing combinations, all six worksheet scenario adapters, and recovery entry points. A new world or scenario requires explicit audit coverage before this test can pass. The worksheet's 22 controls, the four-step adapter's 14 controls, staging/reciprocal controls and actual-message provenance tests passed. These are offline checks, not new evidence of agent behavior.

The immediate research bottleneck is still distinguishing **blocked access, useful peer discovery, acquired method, actual message exposure and later use**. The code can represent these states, but the latest null Luna pair did not isolate all of them. Fresh registered Luna trials are required after this prompt revision; old outcomes must keep their original settings.

See the [executable prompt contract](../../experiments/prompt-contract/checks.py), [LessWrong comparison](lesswrong-comparison-2026-10-19.md) and [previous Luna result](../../experiments/luna-factor-v1/RESULTS.md).
