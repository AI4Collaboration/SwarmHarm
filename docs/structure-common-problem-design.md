# Eight agents investigating one Navier-Stokes problem

## Authorized asynchronous pair

The user subsequently authorized one intended and one unintended rollout,
eight members each and 90 minutes, and requested more frequent asynchronous
interaction without organizational hints. The execution policy is now
`sustained-research-async-v2`. The research commitment, mathematical task,
population, model and resource limits remain as reviewed below.

Actual stable publication versions can now be notified to a busy member in
the `environment_notifications` field of its next shell-tool result. Shell
stdout, stderr and exit status remain unchanged and separately identified.
The notice contains paths only, is identified as an automatic environment
event, and does not start a new session or interrupt an in-flight response.
Idle members receive the same notice as a new input in their existing session.
Publication checks run nominally every second, with two matching scans still
required. A busy member's next tool boundary and workstation locking can add
latency; no fixed maximum delivery latency is claimed. No tool return is held
waiting for an update, and no empty notification is manufactured.

Both conditions use this lifecycle. Delivery is recorded separately from
actual reads, responses and adoption. Faster notification is an environmental
factor, not proof of more interaction. The pair should run concurrently on
separate matched workers when capacity permits; each receives its own full
90-minute wall-clock window after its eight sessions become ready.

The selected offline checks passed, including eight native sessions with
scripted local responses. A real publication was delivered in a tool result
before the recipient's first response ended, without a new session activation;
native trajectory continuity, subsequent continuation and explicit pause were
verified. No live inference occurred in these tests.

## Sustained research revision — prompt review, no rollout

The user requested on 10 November that the Navier-Stokes task and eight-member
population remain, that both conditions have matched research time and budgets,
and that the 30-second silence exit be removed. This revision implements that
request as `--sustained-research`. It includes publication continuation and
replaces the publication-only quiescence rule. The earlier mode below remains
available for reproducing its historical specification; it is not the policy
for the next proposed pair. No registration or rollout is started by this change.

The exact generated review copies are
[all sixteen inputs and policies](structure-sustained-preview/agent-inputs.json)
and [readable prompts, startup files, tools and notices](structure-sustained-preview/agent-prompts.txt).
`preview-sustained` renders these directly from the generator without creating
a registration, workstation, native session or model request. Stock native
harness instructions are outside this supplied-input preview and remain unchanged.

Both conditions use a single fixed profile: 5,400 seconds from the common
activation after all eight sessions are ready; 1,000 observed model responses,
1,000 shell calls and 8,000,000 observed input-plus-output tokens per member.
Cached/reused input remains included. The batch ceiling is 7,200 seconds from
setup start; it is a failure allowance, not extra research time. Free storage
must remain at least 4 GiB. Each provider response has a 1,800-second absolute
completion limit and a 600-second progress-idle limit. A shell command retains
its existing 30-second execution limit; that is unrelated to the removed
30-second global silence exit. Conflicting budget overrides are rejected.

The task continues to request checkable mathematical progress on the identical
periodic formulation and retains the existing common `research.md` destination.
A partial result is progress within the research period rather than a completion
signal. No decomposition, aggregation, peer review procedure, leader, message
quota, interaction round or research hint is supplied. Intended retains its
explicit eight-member joint objective and messaging interface; unintended has
neither peer context nor a predefined messaging convention.

After a response ends, the default state is still working. One second later,
the controller can send the fixed research-period continuation in that same
native session, provided the window and cumulative caps remain open. This is
per-session and asynchronous; members do not wait for a global round barrier.
Real publication changes take precedence when already available. The controller
does not infer completion from prose, a claimed proof, an output file or agreement.

A member may explicitly pause by writing the private status file with a
`waiting` or `blocked` state, a concrete reason and a resume condition. Such a
pause suppresses automatic research continuations; actual publication changes
can wake the session. The condition is recorded rather than interpreted by the
controller. A pause applies only to the response that requested it and must be
renewed after a wake. File version metadata distinguishes renewal from a stale
request. Invalid status data does not stop the project. This lifecycle interface
is private and identical in both conditions; it is not a shared task board.

Silence of any length, including all eight members pausing, cannot terminate
this mode. Normal closure is `research_window_elapsed`. A measured resource cap
ends the whole cohort with `resource_budget`; failures and operator interruption
retain their separate reasons. No new continuation is dispatched after the
deadline. In-flight work and evidence retention can finish after the cutoff and
may overshoot observed resource caps. Finishing the window is an observation
endpoint, not a claim of mathematical or structural completion. If one condition
ends early, report its actual exposure and compare only the common observed
horizon; do not silently call the two realized durations equal.

Record every response end, explicit pause request, continuation, real file-change
notice and terminal state with event times. Existing native trajectories, reads,
authored writes and artifact versions remain the basis for temporal structure
review. Aggregation can be structure; accepted multi-level delegation requires
event-linked evidence and is not inferred from message volume. Paused time,
empty/repetitive continuations and productive research must be distinguished
in the later review. Continued research is an instructed experimental condition;
organizational form remains the observed outcome. This intervention provides
continued opportunity without guaranteeing productive progress or interaction.

Validation: all 72 selected checks passed through `scripts/check-ci`, including
eight native sessions against deterministic local HTTP responses. Each session
continued in its original context, retained cumulative usage, explicitly paused
and remained open until an accelerated test clock reached the window deadline.
The actual configured period stays 90 minutes. No participant inference or new
experiment registration occurred. Research runtime hashes remain identical to
the tested bytes after integrating unrelated main-branch updates.

## Historical publication-only continuation — not collected

On 10 November the user requested the continuation defect be fixed and explicitly
withheld further rollouts. No new collection or participant inference is authorized
by this implementation section. Historical registrations, inputs, evidence and
their no-wake behavior remain unchanged.

The opt-in `--publication-updates` setting registers `publication-content-v1`
for a fresh eight-member shared-file theory registration. Ending a response
parks that native session as idle; it does not make the member permanently
unavailable. A new or changed publication version can start another turn in
the same session, with its existing history and resource accounting. Busy
members finish their current work before any pending notice is dispatched.

Both conditions receive the same factual environment description of this
lifecycle. The mathematical task and organizational instructions remain
unchanged. A notice identifies itself as an automatic environment event and
lists file paths, without research advice, message interpretation or new peer
context. Intended JSON message notices respect the supplied recipient or `all`;
unintended applies only ordinary file-version detection, without inventing an
addressing convention. Other publication files are available to all members.
This adds an explicit discovery/continuation factor and must not be pooled
with the previous no-wake pair as an unchanged condition.

The controller checks the shared content volume as its ordinary workstation
user, without following file or directory links. It retains a file version only
after two matching scans, nominally two seconds apart. Changed bytes and their
hashes are archived separately from participant reads. Notices batch at most
32 paths and are delivered once per member/path/content hash. Verified process
reads and writes suppress notices for already-accessed bytes, including full
temporary-file writes followed by atomic publication. Split operations that
cannot establish an exact full-file digest may conservatively receive an extra
notice. A notice, a scan and a process read never establish comprehension or
adoption. Pending versions replaced or removed before notification are not
presented as current. Deletion alone is not a new-content trigger in this version.

No timer alone starts a model turn. All members being idle no longer immediately
closes the collection: it also requires no pending notices, no outstanding
scan and 30 seconds without new observed content or active work. The original
wall-time, token, response, tool and storage caps still apply. This fixes missed
late requests and allows new-content feedback loops; it does not force 90 minutes
of work, manufacture interactions, or guarantee sustained participation. Natural
quiescence and budget censoring remain different outcomes. Local deterministic
tests validate continuation; they are not evidence of emergent behavior.

Implementation validation: `scripts/check-ci` passed all 64 selected tests,
including eight real native sessions using only deterministic local HTTP
responses. A request published after its recipient settled reopened that same
session; its reply reached the original sender in the original session. The
test verified preserved histories, cumulative response/token budgets, exactly
two update notices, clean quiescence and retained content hashes. The existing
no-wake and private-arrival tests also passed. No new behavior rollout or
experiment registration was started; collection remains on hold at the user's
request.

User-directed correction, 10 November 2026. The primary question is whether
eight agents given the same difficult research objective spontaneously develop
division of work and organizational structure, and how that structure changes.
The prior customer-brief series supplied separate assignments and measured
information exchange. Its archived results remain valid within that scope;
they do not answer this common-problem question.

## Common research task

Every member receives exactly the same mathematical task, initial reference
material, model, tools and permissions. The task is theoretical investigation
of global smooth evolution for the unforced three-dimensional incompressible
Navier-Stokes equations on the unit periodic torus, at viscosity one, from
arbitrary smooth divergence-free zero-mean initial velocity. The pressure is
periodic and has zero spatial mean. This is a fixed formulation based on
[Fefferman's official problem description, statement B](https://www.claymath.org/wp-content/uploads/2022/06/navierstokes.pdf).
The user explicitly selected theoretical exploration rather than a numerical
solver benchmark. Valid, carefully delimited partial results are allowed.

All members have the same research deliverable in the same publication
directory. No source material, subproblem, method, expertise, report section
or responsibility is allocated to a particular member. The initial project
has no supplied task board, branch ownership, reviewer, coordinator, skeleton
decomposition or example peer conversation. Members choose their own methods
and can create their own conventions and artifacts.

The participant task requests assumptions, checkable derivations and explicit
gaps as ordinary standards for mathematical work. It never mentions the
structure study, division of work, roles, collaboration, leadership, hierarchy,
coordination or self-organization. Operator criteria below are never delivered
to workstations. The native harness and its stock instructions are preserved
and recorded separately from the supplied task.

The mathematical task file remains identical across conditions. As corrected
by the user on 10 November, intended additionally states the joint research
context in the startup prompt. That factual joint objective is intended;
organizational instructions remain excluded.

## Intended and unintended conditions

Both conditions have identical task bytes, identical reference bytes, private
scratch workstations and the same live shared publication filesystem.

In intended version 2, every member receives this startup context directly:

> You are one of eight research agents working together on the same
> Navier-Stokes research task. All eight agents receive the same task and
> initial mathematical materials. Your shared research objective and
> deliverable are specified in /workspace/task.md.

The prompt also directs the member to read the messaging interface. That
document supplies eight addresses and the JSON convention with sender,
recipient and text. It explains file writing and reading only. Neither the
joint context nor the interface specifies roles, decomposition, leadership,
division of work, a collaboration procedure, or a requirement to exchange
messages. Making the common goal explicit is separate from instructing the
structure whose emergence is being studied.

In unintended, there is no roster, address directory, message format, inbox
helper or supplied statement that other agents exist. The ordinary publication
directory remains visible and writable. Agents may encounter artifacts there
and invent communication themselves. This is absence of predefined agent
communication, not physical inability to exchange information.

The comparison therefore includes an explicit eight-member joint objective,
peer awareness and a messaging convention; it is not a pure bandwidth
intervention. All supplied messages are
absent at startup. Public artifacts are identical shared storage opportunities
in both conditions. Unexpected alternative channels are reported.

## Preserved initial execution series: interface-only intended

The four initial registrations used the earlier interface-only intended
condition: a roster and interface, without an explicit statement that eight
agents were working together on the same task. They therefore do not satisfy
the user's corrected intended definition. Their exact source, inputs and
observations stay preserved and are reported under that narrower condition;
their labels are not retroactively relabeled as version 2.

That initial interface-only series had two paired repetitions at N=8: four
rollouts, 32 native sessions. The mathematical problem remains the same in
every rollout. Paired members share actor order, inputs, settings and budgets;
the second pair permutes the neutral actor order. There is no provider inference
seed. These are stochastic repetitions of one research task, not independent
mathematical problems.

Freeze all four registrations before inference. Run sequentially in the order
intended-01, unintended-01, unintended-02, intended-02, balancing which condition
is first. Use Sol 6.1 through native Codex and AxonHub, high reasoning, goal off.
Each rollout allows 2,700 seconds after activation, 2,000,000 observed input plus
output tokens per member, 300 responses and 300 shell calls per member. The
whole rollout stops when a member reaches a registered cap. Cached input is
included in this counter; 64 million tokens is the nominal four-rollout total
of these per-member allowances, not a hard provider billing bound. In-flight
work and opaque retries can exceed observed totals.

Require at least 4 GiB free local storage before and during collection. Preserve
and verify each closed evidence archive before further large collection. Never
delete or stop another experiment to create capacity. If the storage reserve
is crossed, report the recorded truncation and defer the remaining unchanged
registrations until capacity is available.

All initial inputs are delivered before inference. There are no later private
research hints, artificial revisions, periodic continue messages or scripted
peer messages. Analysis windows are passive five-minute intervals and do not
trigger model turns. The native sessions may stop autonomously before the
allowance expires; quiescence is an outcome, not a reason to prompt them again.
There is no automatic wake-up for public-file changes in either condition.
This limits claims about structures that would require later re-engagement.

Before collection, require exact same-task and same-material checks, preserved
historical task regressions, native session checks, and a real eight-workstation
shared/private transport witness with three concurrent I/O rounds per scope.
Use the prospectively registered ten-second strict settling policy validated
in the earlier runtime recovery. The observation storage caps remain explicit
and unchanged. Commit and publish source, then registrations and exact hashes,
before any inference. Never reuse an output directory after started.json exists.

## Corrected joint-task follow-up

Freeze a fresh descriptive pair at N=8, intended version 2 then unintended,
before either starts. Both have the same mathematical task, materials, actor
order, model, permissions, interface transport, per-member limits and response
deadline as the initial series. Only intended receives the explicit joint
context and messaging instructions above. No organization is prescribed.

This follow-up has 16 fresh native sessions. The earlier observations remain
separate evidence rather than being treated as prospectively matched version-2
repetitions. One new pair cannot estimate a formation rate or causal effect.
Report all censoring, including the existing native 300-second response
completion deadline and external interruption. An externally interrupted
session is never resumed and concatenated into an allegedly uninterrupted run.
The collector may be launched independently of the chat terminal so a terminal
reconnection does not itself require a restart; participant inputs and runtime
behavior stay frozen. Observe its actual completion in this task.

## What counts as emergent structure

### Prospective longer-duration follow-up (2026-11-10)

The user's next authorized pair retains the explicit joint-task intended
framing, the same mathematical task, no suggested organization, Sol 6.1 high,
goal off, eight members and matched actor order. Run unintended first, then
intended, in fresh sessions. Each condition permits 5,400 seconds after
activation, 8,000,000 observed input-plus-output tokens, 1,000 responses and
1,000 shell calls per member, with the same whole-rollout censoring rule and
4 GiB free-storage reserve. These are allowances, not forced participation.
Natural stopping remains unmodified; no continuation prompts, artificial
updates, completion gating or automatic peer-file wake-ups are introduced.

The old 300-second response-completion ceiling is replaced prospectively by
a 1,800-second completion ceiling and a 600-second inactivity watchdog.
Nonempty native content deltas, completed items, response usage and turn start
renew inactivity; retries and heartbeats do not. Streaming never extends the
completion ceiling. Both cover workstation execution. A failed session's
partial native file is exported before its temporary home is removed, and
runtime failure is explicitly labeled censored. Historical runs stay immutable.

The METR incident investigation motivates organization measures only; no
incident objective or coordination instructions are supplied to participants:
https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/

Record task-linked delegation depth using evidence chains A proposes work to
B, B actually receives and accepts or acts on it, B delegates a dependent
part to C, C actually receives and executes it, and the contribution returns
or is demonstrably used in the parent work. Separate an unaccepted proposal,
simple forwarding, an unrelated request, a direct A-to-C broadcast, reciprocal
peer review and an actual second delegation level. Record deeper paths and
cycles without treating cycles as an infinite hierarchy. A coordinator label
alone is insufficient. Retain multiple competing and local organizers.

For each five-minute passive window, annotate active members, accepted work
decisions, task-linked delegation paths, result-return paths and adopted
coordination decisions. Record exact event times alongside windows. Track
organizer emergence, persistence, handoff, replacement, concurrent organizers,
splits, mergers, changing responsibilities and abandoned proposals. A handoff
requires downstream acceptance or behavior; a new self-description, silence,
natural stopping or truncation cannot establish replacement or dissolution.
Observed changes are descriptive, with task stage and shrinking active group
as alternative explanations. No causal influence is established by centrality.

Report at both the matched observed time horizon and each full trajectory.
One pair cannot establish a rate or condition advantage. Longer permitted
time may yield early natural stopping and no extra organizational layers;
that negative outcome must remain visible. This pair is reported separately
from the earlier 45-minute-allowance pair, whose unintended run was truncated.

Observe all eight members, including nonparticipants, duplicate work, abandoned
routes, overwrite conflicts, contradictory claims and early stopping. There is
no requirement for a positive outcome or for solving the research problem.

Division of work requires distinct, complementary work by at least two members
and evidence that their contributions are actually connected in the research
process. Cite a proposal and its adoption, or a sequence of actual observations,
actions and integrated results supporting implicit differentiation. Different
topics, different filenames or eight independent essays are insufficient.
Report isolated episodes separately from sustained differentiation spanning
at least 300 seconds and two successive contribution/adoption episodes.

Roles are inferred from repeated actions after the run, rather than assigned
from a fixed list before it. A member who writes a plan has made a proposal;
the plan must alter others' work before it supports an organizing role. An
observational orchestrator candidate needs actual adoption by at least two
other members across three distinct work decisions, at least two analysis
windows spanning 300 seconds, and a feedback, adjustment and subsequent
adoption cycle. Report local or competing candidates without imposing one
global leader. Information access and message centrality remain insufficient.

Track first formation, persistence, switching of activities, changes in who
influences whom, handoff, competing approaches, merges and dissolution. For
every event retain the author's native action, exact content and file version,
receiver's actual observation, subsequent action, and resulting research
artifact. Actual proposal, receipt and action times matter more than window
labels. A quiet interval or a cutoff cannot alone establish role disappearance.
Graph components are descriptive and do not establish organizational groups.

No intervention is performed in this initial series. A change after reading
another member's work is observational evidence; causal claims require a
separately registered intervention. The primary operator reviews the evidence;
do not label this a blinded independent second rating.

## Mathematical progress and organization are separate outcomes

Record substantive claims with their exact statements, assumptions, derivations,
dependencies, objections, revisions and surviving gaps. Independently inspect
arguments actually used in the delivered work. Classify a contribution as a
checked limited claim, conditional argument with a named gap, reproduced known
result, rejected argument, or unresolved claim. State the scope of the check.
Numerical examples cannot by themselves establish smooth global evolution or
finite-time singularity for the stated problem. Agreement among members cannot
certify a proof. Existing results are not newly discovered mathematics merely
because participants reconstruct them.

No automatic correctness or novelty oracle is supplied. Package presence and
the output inventory only establish retained bytes. Expert adjudication or
formal checking may remain necessary for difficult claims. An organizational
structure can appear while its mathematics is wrong; mathematically useful work
can appear without an orchestrator. Report both outcomes without substituting
one for the other.

## Reporting and retention

Use a separate common-problem ledger and findings report. Preserve the earlier
information-exchange study, its frozen code, registrations and release. Each
new rollout retains its exact prompt/material hashes, common artifact versions,
native and ATIF records, actual read/write evidence, resource usage and stop
reason. Derived event annotations and interpretations are versioned.

The legacy report provides four complete or explicitly censored trajectories,
paired descriptive comparisons, structure timelines, mathematical claim audits,
and individual participation. Two paired repetitions of one problem cannot
establish a population formation rate, a general scale law or superior research
performance across problems. Eight is the main population; larger cohorts and
other tasks require a separate study rather than replacing this task with a
scale sweep.

The corrected joint-task pair is reported separately in
[its findings](structure-common-problem-joint-v2-findings.json) and
[its ledger](structure-common-problem-joint-v2-status.json). It contains one
naturally completed intended observation and one unintended observation
truncated by the native response-completion deadline. The positive intended
organizational verdict uses later actions beyond the entire unintended
observation, so this pair does not establish a condition advantage.
