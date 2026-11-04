# Phase 1 taxonomy: autonomous communication channels

Phase 1 asks whether initially separate agents establish usable communication
through ordinary capabilities and form a connected swarm. This note maps candidate
channel families before selecting further scenarios. No environment, prompt,
registration or frozen formation score changes with this classification.

The single classification axis is **which observable carries the information
that the receiving agent interprets**. The four proposed families are **authored
content, environmental state, observable actions, and timing**. This is our
operational synthesis of established research, not a four-way taxonomy stated
by one authoritative source. The classes are possibilities, not four mandatory
experiments. The [JSON taxonomy](phase1-communication-taxonomy.json) uses the same
definitions. Business domains are scenario labels, not additional classes.

## What agents establish

A usable channel needs a causal path from an agent's action to another agent's
observation. Ordinary infrastructure can supply that path. Agents must discover
or construct its communicative use and engage through it; physical transport
need not be invented from nothing.

Generic read/write, business-state and event interfaces are compatible with
this goal. A ready-made peer inbox supplies an interpersonal communication
facility: using it alone demonstrates channel use. An agent-created mailbox
or service can demonstrate channel construction if others discover and use it.
The distinction depends on initial capabilities and subsequent behavior, not
the tool's name.

Existing language is allowed; a new code, handshake or language is not required.
Tasks prescribe no communication, peers or signaling convention. Ordinary
documentation and factual notifications remain available.

## C1 — Authored content

**Signal:** an agent-selected payload that another agent retrieves and interprets.

Shared documents are one implementation. Other candidates include business
annotations, artifact descriptions, source attachments, repository changes,
database values and agent-created mailboxes. Payloads can be text, structured
data, images or other authored representations. These are variants of one family.

An Engineering instance could let agents encounter ordinary build artifacts
and independently use related records or metadata to exchange missing source
information. No bulletin-board purpose or request procedure is assigned.

**Boundary:** an authored note inside an event record is C1. The system-generated
event type is C3. An arbitrary name carrying a message is content; an object's
mere presence is C2.

**Theory:** shared data spaces support persistent contributions without a
preassigned recipient. Cognitive stigmergy includes rational agents' symbolic
annotations.
[Gelernter, 1985, §§2–2.3](https://www.cs.tufts.edu/comp/150FP/archive/david-gelernter/generative-linda.pdf);
[Ricci et al., 2007, §§3.3–4.1](https://lia.disi.unibo.it/~ao/pubs/pdf/2007/_e4masIII-rovgo.pdf).

## C2 — Environmental state

**Signal:** a current configuration or value of the working environment,
rather than an authored message body.

Candidates include object presence, location, arrangement, links, workflow state
and reservation availability. These states can be persistent or short-lived,
discrete or quantitative. A document is unnecessary.

An Engineering instance could expose a release workspace's configuration or
a release reservation's current state. Agents would have to discover that their
actions affect a state visible to others and use that relationship to communicate.
The experimenter supplies no signaling meaning for particular states.

**Boundary:** a snapshot is C2; observing the actions that produced it is C3;
interpreting its duration is C4. A normal prerequisite becoming ready does not
by itself demonstrate communication.

**Theory:** stigmergy includes changes to the work itself and added markers.
Persistence and qualitative/quantitative traces are established distinctions,
used here as descriptive properties rather than another experiment matrix.
[Heylighen, 2016](https://researchportal.vub.be/nl/publications/stigmergy-as-a-universal-coordination-mechanism-ii-varieties-and-/).

## C3 — Observable actions and events

**Signal:** which action happened, or its place in an action sequence, observed
directly or through ordinary business events.

Candidates include validation attempts, artifact publication, selection changes
and reservation events. A fixed-format event stream can expose these without
a free-text send-to-peer interface.

An Engineering instance could expose ordinary CI lifecycle events. Agents would
need to discover communicative significance in each other's choices and respond
through their own actions. Receiving an automatic build report alone does not
demonstrate that an action was used to communicate.

**Boundary:** action identity or order is C3 even if a log stores it. An authored
payload is C1; a current snapshot without action history is C2; intervals are C4.

**Theory:** communication-through-actions research studies both interpreting
others' choices and choosing actions to convey information. Tian et al. use
learning and an auxiliary reward; Wang et al. use a centralized action/message
mapping in their training framework. These works establish the mechanism, not
autonomous discovery under our neutral tasks.
[Tian et al., AAAI 2020](https://arxiv.org/abs/1810.04444);
[Wang et al., 2025 revision, §§3–4](https://arxiv.org/html/2411.01553v2).

## C4 — Timing

**Signal:** action timing, duration, inter-event intervals or service latency,
rather than payload, state identity or action identity alone.

Possible business substrates include observable job scheduling and completion
times. Agent behavior must influence the temporal quantity interpreted by the
receiver. Unexplained service noise is not an authored signal.

**Boundary:** a busy/available label is C2; its duration can be C4. An event order
that does not depend on elapsed time is C3. Timing can accompany other families.

**Theory:** timing channels are established in information theory, including
information carried through queueing systems.
[Anantharam and Verdú, 1996](https://collaborate.princeton.edu/en/publications/bits-through-queues-2/).
That theory does not establish usability at our models' decision times.

This candidate family does not restore competition, manufactured delay, quota
changes or the earlier resource experiments.

## Agent-created messaging facilities

Using general programming capabilities to create a mailbox, service or rendezvous
that others subsequently discover is another concrete route beyond editing a
pre-existing document. Its payload is C1; creation and discovery are properties
of the trajectory, not a fifth signal family.

Dynamic channel creation and name passing have a formal account in π-calculus.
That account models communication structure, not an LLM's motivation or ability
to discover an endpoint.
[Sewell, 2000, ch. 1](https://www.cl.cam.ac.uk/~pes20/apppi.pdf).
Feasibility depends on ordinary programming and connectivity capabilities;
this research enables no new interface.

## Classification rules

Classify an exchange by the observable its receiver interprets, not by the
storage product or tool name. A mixed path can use more than one existing class.

- A queue can expose payloads (C1), membership (C2), business events (C3), or
  timing (C4). A queue alone is not a class.
- A lock's state is C2, a release event C3, and duration C4. Locks and compiler
  pools are implementations, not additional signal families.
- A factual record-change notice can lead to a C1 content read. It is not an
  extra authored exchange solely because it wakes an agent.
- Polling/notification, persistence, modality and channel origin are attributes,
  not another scenario taxonomy.
- Supplied peer messaging demonstrates channel use; agent-created messaging
  may demonstrate establishment. Business terminology alone decides neither.

The older shared-space/message-passing contrast describes implementation
architecture, not the active signal taxonomy.
[Stone and Veloso, 2000, §2.1](https://www.cs.cmu.edu/~mmv/papers/MASsurvey.pdf).
Notification support is compatible with shared spaces.
[Eugster et al., 2003, §§3.4–3.5](https://cse.hkust.edu.hk/~charlesz/comp610/paper/p114-eugster.pdf).

## Existing evidence and candidate scope

The twelve-rollout native comparison contains eight registered formation passes
covering four business scenarios. Its positive exchanges use C1 through ordinary
shared records. Original scores and separate source-specific reassessments remain
in the [native comparison](phase1-native-sol-terra-luna-full-20261104.json).

Data Luna r97 contains **143 → 155 → 182 → 194**, a source-bound
request/read/reply/readback. Its initial documentation already explains lookup,
annotation, linked updates and factual notices. These are supplied affordances;
the interpretation of independently establishing communication must consider
those surfaces alongside behavior. An API name alone cannot settle it.
[Frozen initial files](../../../eval-readiness/phase1-full-data-luna6-codex-r97/initial-file-audit.json).

Knowledge Luna r103 contains **420 → 429 → 435 → 441**, then source retrieval
at **448**. A factual notice supports awareness; the subsequent read provides
authored content.
[Trace-backed findings](phase1-publication-analysis.md#trace-evidence-for-the-findings).

These results do not establish autonomous C2/C3/C4 channels. Historical operator
demonstrations and passive effects remain separate. Additional C1 implementations
can broaden practical coverage without adding a class.

Further scenario selection is a research-scope decision. Taxonomy expansion
neither authorizes collection nor makes every family a publication requirement.
The current task is taxonomy research; frozen metrics and live environments stay
unchanged.
