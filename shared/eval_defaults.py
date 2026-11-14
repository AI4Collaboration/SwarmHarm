"""The default handoff: all lineup models, both studies, one repeat at each N."""
POPULATIONS = (4, 8, 16)
REPEATS = 1
GOAL = 'off'
REASONING = 'high'
TASKS = ('decoder-compatibility', 'decoder-release', 'jq-reconstruction',
         'service-plan', 'customer-briefs', 'robust-planning')
CHANNELS = ('direct', 'filesystem', 'socket', 'mapped_memory')
SCENARIOS = ('engineering-capacity', 'knowledge-work')
MECHANISMS = ('task-gaming', 'evidence-tampering', 'grader-manipulation',
              'information-authority', 'action-authority', 'shared-capacity')


def settings():
    return dict(populations=list(POPULATIONS), repeats=REPEATS, goal=GOAL,
                reasoning=REASONING, api_protocol='chat-completions',
                swarmform=dict(tasks=list(TASKS), channels=list(CHANNELS)),
                swarmharm=dict(scenarios=list(SCENARIOS), mechanisms=list(MECHANISMS)))
