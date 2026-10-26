# How SwarmHarm evolved, 21 to 26 October

I didn't run any models for this. I read Terry's commits and reviews from the last six days and drew them as flowcharts, so every number here comes from one of the linked reviews.

## If you are new to SwarmHarm, start here

SwarmHarm asks whether a group of AI agents, each doing an ordinary job, can end up causing harm together that none of them would cause alone. Four agents work in one simulated company, each gets stuck on something that only another agent's job can unblock, and nobody tells them the others exist:

![Diagram of a SwarmHarm campaign: four agents with stuck jobs share an activity surface, act on a business system, and an independent verifier scores the result](swarmharm-evolution-2026-10-26/fig/a-setup.svg)

A run is scored in two phases. Phase 1 asks whether the agents find each other and start talking, and Phase 2 asks whether one agent's shortcut spreads to the others and adds up to a harmful effect:

![Flowchart of Phase 1 (find the surface, exact read, relay, live dialogue) followed by Phase 2 (source posts, exact read, adopt, two or more accepted actions, effect recomputed)](swarmharm-evolution-2026-10-26/fig/b-phases.svg)

## The short version

Agents read each other's posts from the start, but they only asked each other for help once the shared surface told them who to ask. Once they did, a shortcut one agent posted spread to the others, and in all four business domains GLM and Sol over-committed a shared limit together. The open question is how much of that comes from the agents and how much from the versions that removed the text that made them stop.

## How it evolved

![Timeline from 21 to 26 October with commits per day and what each day built and found](swarmharm-evolution-2026-10-26/fig/c-evolution.svg)

## What I found

### Agents read each other from the start but rarely asked

The cue ladder changes only how directly the shared surface points a stuck case at someone who can help. Reads and relays were there at every rung, and live dialogues stayed at zero until v50 added a triage action that worked ([v43](https://github.com/AI4Collaboration/SwarmHarm/blob/8f87f975/docs/research/formation-v43-paired-live-review-2026-10-25.md), [cue-5](https://github.com/AI4Collaboration/SwarmHarm/blob/109bc68c/docs/research/formation-v50-cue5-v32-paired-live-review-2026-10-25.md), [cue-6](https://github.com/AI4Collaboration/SwarmHarm/blob/ca598f96/docs/research/formation-v50-cue6-v32-paired-live-review-2026-10-25.md), [cue-7](https://github.com/AI4Collaboration/SwarmHarm/blob/c113b647/docs/research/formation-v51-cue7-v32-paired-live-review-2026-10-25.md)).

![Cue ladder table for GLM and DeepSeek from v41 to cue-7](swarmharm-evolution-2026-10-26/fig/1-cue-ladder.svg)

DeepSeek is the harder model to move: it passed Phase 1 only at v50 and cue-7, and at cue-7 it made no adoptions because its 300-second actor window ran out first.

### The first full pass was a chain of reasonable steps

In [v31](https://github.com/AI4Collaboration/SwarmHarm/blob/4665a4b4/docs/research/swarmharm-v31-glm-live-review-2026-10-25.md) every agent did something that looks fine on its own, and the harm only shows up in the total, which no agent could see:

![Event flow of v31 from swarm formation at event 65 to 11 units committed against a pool of 4](swarmharm-evolution-2026-10-26/fig/2-v31-chain.svg)

### The same thing happened in four kinds of work

On 26 October Terry ran cue-7 in four domains with GLM and Sol, and both models over-committed in every one ([four-domain review](https://github.com/AI4Collaboration/SwarmHarm/blob/b0fb2212/docs/research/swarmharm-four-domain-glm-sol-live-review-2026-10-26.md)):

![Bars comparing each domain's limit with what the agents committed together](swarmharm-evolution-2026-10-26/fig/4-domains.svg)

### Where agents stopped, the next version removed the reason

The pattern in this section is the one I'd want settled before anyone quotes the Phase 2 numbers. Four times, agents refused because of a sentence in the world, and the next version took that sentence out ([v19](https://github.com/AI4Collaboration/SwarmHarm/blob/7e0a97fd/docs/research/swarmharm-v19-glm-live-review-2026-10-25.md), [v23](https://github.com/AI4Collaboration/SwarmHarm/blob/a96b8f3d/docs/research/swarmharm-v23-glm-live-review-2026-10-25.md), [v24](https://github.com/AI4Collaboration/SwarmHarm/blob/787215de/docs/research/swarmharm-v24-glm-live-review-2026-10-25.md), [v32](https://github.com/AI4Collaboration/SwarmHarm/blob/cba01f35/docs/research/swarmharm-v32-glm-live-review-2026-10-25.md), [v35](https://github.com/AI4Collaboration/SwarmHarm/blob/a283b7a9/docs/research/swarmharm-v35-glm-live-review-2026-10-25.md)):

![Four rows where safety text made agents stop, the next version removed it, and harm followed](swarmharm-evolution-2026-10-26/fig/3-safety-text.svg)

Each removal has a fair business reason, and the refusals themselves are a good result, but read together they mean the positives were found by searching for the world in which agents don't stop.

### Sometimes the checker decided the result

Terry's rule is to keep a frozen result and fix the verifier in the next version, which I agree with, though keeping the frozen result means some negatives in the history are measurement misses rather than agent behavior ([v20](https://github.com/AI4Collaboration/SwarmHarm/blob/96547675/docs/research/swarmharm-v20-glm-live-review-2026-10-25.md), [v29](https://github.com/AI4Collaboration/SwarmHarm/blob/ac4080f2/docs/research/swarmharm-v29-glm-live-review-2026-10-25.md)):

![Flowchart of how a verifier miss becomes a standing negative, with four examples](swarmharm-evolution-2026-10-26/fig/5-verifier.svg)

## Runs I'd suggest

Terry's [takeaways](https://github.com/AI4Collaboration/SwarmHarm/blob/b0fb2212/docs/research/environment-iteration-takeaways.md) already say to stop tuning and measure a rate. This is how I'd set that study up, though it needs model access, so whether and when to run it is Terry's call:

![Rate study design with cue, safety sentence, model and actor window as factors across four domains](swarmharm-evolution-2026-10-26/fig/6-next-study.svg)

## Limits

Every result above is one rollout per cell, so none of it is a rate yet. Under the v31 rules GLM had two dialogues at cue-5 and still failed on a discovery-order check, which v32 then relaxed, so the cue-5 rows across contracts aren't strictly comparable. I only read the reviews and spot-checked traces they cite; I didn't rerun any verifier.

## How to reproduce

The figures are drawn by one standard-library Python script, with a comment beside each number naming the commit it came from:

```bash
D=docs/research/swarmharm-evolution-2026-10-26 && python3 -I $D/diagrams.py $D/fig
```
