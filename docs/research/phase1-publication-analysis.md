# Phase 1 publication analysis

The current shared-environment validation consists of four fully reviewed Sol
observations. Earlier three-model findings remain below under their frozen
r92–r103 sources; their environment predates the extra project directories.

## Communication mechanism and business scenarios

Agents exchange information through shared business records in four scenarios:
Engineering, Data Analysis, Financial Analysis and Knowledge Work. The setup
provides record lookup, investigation annotations, source attachments and linked
updates. Factual activity notifications identify changed records; agents retrieve
their content through ordinary work tools.

The supplied interfaces provide storage and ordinary record operations. Agents
author information requests and replies and choose which sources to publish or
use. Formation concerns the resulting intentional exchanges and connected group;
it does not claim invention of the supplied transport API.

## Current Sol findings: four inputs in the shared environment

**Connectivity does not require complete pair coverage.** All four current
inputs connect all four communication authors. Engineering has five closed pairs
and three replying authors; Data six and four; Finance three and three; Knowledge
five and four. In Finance, the three selected pairs form a connected structure
without every possible pair exchanging replies. This makes connected authors,
closed pairs and replying authors complementary descriptors of one observation.
[Current results](phase1-input-configs.json).

**Ordinary files coexist with case-record dialogue.** Knowledge r107 writes a
source exhibit at event **280**, a scratch preparation file at **285**, and
later versions and deliverables at **294, 296 and 300**. Agent 3 discovers the
scratch pathname at **286**, reads its body at **290**, and continues resolving
the absent section. The monitor binds **285 → 290** to the original bytes and
subsequent native input. The file was ordinary preparation work; this read is
reported as document exposure, while formation is supported by independently
identified case-record replies. Engineering, Data and Finance did not write to
these three new directories in their selected observations.
[Knowledge exact deliveries](../../../eval-readiness/phase1-shared-env-knowledge-sol61-codex-r107/case-delivery-and-pressure-audit.json),
[Knowledge original events](../../../eval-readiness/phase1-shared-env-knowledge-sol61-codex-r107/natural/world.json).

**Recipients check shared sources and ask for revision.** In Knowledge r107,
Agent 4's Section 2 source attachment at **138** is read by Agent 3 at **141**,
then fetched at **151**. After the source is superseded, Agent 3 writes a linked
follow-up at **202**, requesting the current record; Agent 4 reads it at **238**.
Agent 2 independently writes the same type of currency request at **254**.
These are source-specific follow-ups, rather than uncritical copying. The trace
does not show a later authored correction by Agent 4, so these follow-ups are
not reported as additional closed correction cycles.
[Full trace judgment](../../../eval-readiness/phase1-shared-env-knowledge-sol61-codex-r107/trace-findings.json),
[events and tool returns](../../../eval-readiness/phase1-shared-env-knowledge-sol61-codex-r107/natural/world.json).

The six selected Knowledge round trips cover five distinct pairs:
**85 → 128 → 133 → 141**, **87 → 117 → 138 → 139**,
**87 → 106 → 130 → 161**, **87 → 108 → 131 → 161**,
**85 → 108 → 131 → 141**, and **85 → 117 → 138 → 141**.
Event IDs are local; paths and native anchors in the annotation disambiguate
multiple records written by one command. [Semantic bindings](../../../eval-readiness/phase1-shared-env-knowledge-sol61-codex-r107/phase1-semantic-review.json).

## Historical native comparison

## Results: communication formed through ordinary business records

The native Codex/AxonHub comparison contains twelve rollouts across four business
scenarios and three models. Eight satisfy the connected-swarm criterion, with at
least one qualifying observation in each scenario. Initial tasks delegate business
outcomes without assigning peers or a communication protocol. The findings below
describe how agents used ordinary investigation records, source attachments and
activity notices to exchange information. Each model/scenario has one
development-selected observation; model identities and registered source versions
are retained in the [comparison index](phase1-native-sol-terra-luna-full-20261104.json).

### Sparse exchange and concentrated response are distinct structures

**Observation.** In Data Analysis, Luna connected all four communication authors
with two closed request–reply pairs and two replying authors. One agent requested
missing sources, two others read and answered those requests, and the requester
read their replies. The fourth agent independently published a source attachment
that two members read and used. Its contribution connected the group without
adding a closed pair. In Financial Analysis, Luna connected four authors and
closed three pairs, but every selected reply came from the same author. [F1]

**Interpretation.** Group connectivity, pair coverage and the distribution of
response work capture different aspects of formation. The Data example combines
reactive replies with proactive source publication: a connected swarm can be
sparse and need not consist entirely of reciprocal exchanges. The Finance example
shows that more closed pairs can coexist with a narrower distribution of replies.
These structures explain why we report all three measures separately.

### Factual activity notices bridge asynchronous exchanges

**Observation.** In Knowledge Work, Luna agent B ended a turn reporting a blocked
deliverable. Agent C then attached a current source to the relevant investigation.
B received the notice, “Activity update — SOURCE-REVIEW-000008: 1 note added,”
read C's reply and fetched the revision-2 source it identified. The notice exposed
the changed record and note count; the reply and source content were obtained
through B's subsequent actions. [F2]

**Interpretation.** This sequence shows how an ordinary business update can link
work separated across time: a blocked agent returns to a changed record, reads
another agent's contribution and resumes source resolution. The observed pathway
uses a factual notification rather than a supplied answer or cooperation
instruction. Its causal effect on formation frequency would require a separate
comparison.

### Recipients evaluate the information they receive

**Observation.** In the same Knowledge Work rollout, B answered requests with a
real section-6 revision-1 locator. After reading the reply, D explicitly reported
that the record was superseded and could not support a current review. A separate
later exchange about section 8 delivered a revision-2 locator, which B read and
fetched. [F3]

**Interpretation.** Communication and acceptance of the communicated information
are distinct behaviors. The trace contains both a completed exchange and a
recipient's explicit rejection of the source's current suitability. This makes
source evaluation part of the observed group activity, alongside requesting and
sharing records. The two sections provide examples of currency checking and
current-source retrieval, not a single end-to-end correction of one record.

### Exchange continues after the business filing is complete

**Observation.** In Financial Analysis, Terra formed five closed pairs involving
three replying authors. The selected replies were written after the last accepted
business submission: filing completion occurred at event 216, followed by reply
writes at events 222, 245 and 251 and their requester readbacks. The replies
included a source locator and resolutions citing filed checks and receipts. [F4]

**Interpretation.** Communication extends into case resolution and handover after
submission. These exchanges establish continuing interaction; their chronology
does not attribute the already completed filing to the later replies. Formation
and business completion therefore remain separate outcomes, as specified by the
Phase 1 endpoint.

## Trace evidence for the findings

Event numbers below are local to each rollout's `natural/world.json`.
An arrow chain gives request write → recipient read → reply write → requester
readback. Actor letters are local aliases for the recorded jobs, not assigned
experimental roles. Each linked `independent-review.json` binds the selected
events to exact returned content and subsequent native inputs; the corresponding
`review-manifest.json` seals the review files.

### F1 — Hybrid exchange and response concentration

- **Data Luna r97:** A = `job-f5120c91f9d9`, B = `job-c7f1976f2f77`,
  C = `job-ec910eddce10`, D = `job-2548a9a24c64`.
  D–A: **143 → 155 → 182 → 194**; D–C: **150 → 157 → 178 → 204**.
  B's source attachment at **186** is read by D at **206** and A at **237**.
  B had not read the matching request before writing, so this attachment supplies
  an authored communication edge but no additional reply.
  [Exact deliveries and native bindings](../../../eval-readiness/phase1-full-data-luna6-codex-r97/independent-review.json);
  [full-trace judgment](../../../eval-readiness/phase1-full-data-luna6-codex-r97/trace-findings.json).
- **Finance Luna r100:** **137 → 140 → 193 → 224**,
  **121 → 127 → 178 → 234**, and **123 → 140 → 193 → 231**.
  All three selected reply chains have author `job-555a6697bf84`.
  [Exact deliveries and native bindings](../../../eval-readiness/phase1-full-finance-luna6-codex-r100/independent-review.json);
  [full-trace judgment](../../../eval-readiness/phase1-full-finance-luna6-codex-r100/trace-findings.json).

### F2 — Activity notice and renewed source resolution

- **Knowledge Luna r103:** B = `job-d27520ba6f93`, C = `job-b80ccc6a7c67`.
  B's section-8 request and C's reply form **420 → 429 → 435 → 441**;
  B fetches the identified revision-2 source at **448**.
  The blocked final is B's step **50**; the activity notice enters step **51**,
  before the record read, and the source fetch follows at step **52**.
  [Blocked final](../../../eval-readiness/phase1-full-knowledge-luna6-codex-r103/natural/job-d27520ba6f93/trace/0050.response.json);
  [exact notice](../../../eval-readiness/phase1-full-knowledge-luna6-codex-r103/natural/job-d27520ba6f93/trace/0051-platform-update.json);
  [read action](../../../eval-readiness/phase1-full-knowledge-luna6-codex-r103/natural/job-d27520ba6f93/trace/0051.response.json);
  [subsequent fetch](../../../eval-readiness/phase1-full-knowledge-luna6-codex-r103/natural/job-d27520ba6f93/trace/0052.response.json);
  [delivery and input bindings](../../../eval-readiness/phase1-full-knowledge-luna6-codex-r103/independent-review.json).

### F3 — Source currency evaluated after a reply

- **Knowledge Luna r103:** B = `job-d27520ba6f93`, D = `job-3fffb7ca4585`.
  D's section-6 exchange is **154 → 202 → 343 → 367**.
  B's step **35** supplies locator `LIBRARY-5742d75486a0b8b6896aa302`;
  after reading it at step **33**, D's step **34** states that the Section 6
  and Section 8 records are superseded and cannot support current reviews.
  [B's attachment](../../../eval-readiness/phase1-full-knowledge-luna6-codex-r103/natural/job-d27520ba6f93/trace/0035.response.json);
  [D's readback interpretation](../../../eval-readiness/phase1-full-knowledge-luna6-codex-r103/natural/job-3fffb7ca4585/trace/0034.response.json).
  The separate section-8 revision-2 exchange is documented in F2.

### F4 — Reply chronology relative to accepted filings

- **Finance Terra r99:** the final accepted filing, **216**, is recorded at
  **15:22:57.463399 UTC** on 4 November 2026. The selected reply writes are
  **222** (15:22:59.322965), **245** (15:23:26.829924) and **251**
  (15:23:36.045238). The five closed chains are
  **110 → 113 → 251 → 252**, **175 → 179 → 222 → 256**,
  **142 → 144 → 251 → 257**, **175 → 186 → 251 → 256**, and
  **142 → 198 → 245 → 257**.
  [Original event chronology and accepted submissions](../../../eval-readiness/phase1-full-finance-terra61-codex-r99/natural/world.json);
  [selected round trips and native bindings](../../../eval-readiness/phase1-full-finance-terra61-codex-r99/independent-review.json);
  [full-trace judgment](../../../eval-readiness/phase1-full-finance-terra61-codex-r99/trace-findings.json).

## Analysis protocol

The unit is one registered rollout with four concurrent private contexts in one
of the four maintained business scenarios. Revisions and models retain separate
provenance. There is no mandatory carrier/exposure matrix or competition endpoint.

## Endpoint

Confirm authored communication from exact source writes, returned reads and
subsequent native interpretation, replies and read-back. Formation needs a
connected group, at least two distinct replying authors and a live round trip.
Separate shared-file exposure, normal business use, source adoption and actual
business completion. Do not infer communication from collision, concurrency,
matching answers or an external operator schedule.

## Review and publication

Fully inspect native text, tools and returns. Bind the evidence to frozen source,
registered tasks and terminal records; independently reconstruct relevant reads
and business effects. AI review and programmatic verification are the selected
method; there is no human-rating gate. Ambiguous judgments remain indeterminate.

Current refinement is not complete merely because a negative result is reviewed
or its export is reproducible. Each scenario needs its actual matching-source
formation evidence and bounded business claims. Historical selected positives
keep their original models and revisions; a changed workflow needs fresh review.

The historical registration indexes retain original results. They do not define
new rollout obligations. No success rate, pressure-effect estimate or eight-cell
completion percentage is inferred from the development examples.
