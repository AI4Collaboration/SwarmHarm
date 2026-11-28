"""Default model lineup and experiment settings; optional provider ID spelling maps."""
import json
from pathlib import Path

MODELS = {
    'astra': ('openai/gpt-6-astra', 'codex'),
    'sol': ('openai/gpt-6.1-sol', 'codex'),
    'terra': ('openai/gpt-6.1-terra', 'codex'),
    'luna': ('openai/gpt-6-luna', 'codex'),
    'opus': ('anthropic/claude-opus-5.5', 'claude-code'),
    'sonnet': ('anthropic/claude-sonnet-5.5', 'claude-code'),
    'haiku': ('anthropic/claude-haiku-5.5', 'claude-code'),
    'argon': ('google/gemini-4-argon', 'pi-sdk'),
    'kimi': ('moonshotai/kimi-k3.1-pro', 'pi-sdk'),
    'glm': ('z-ai/glm-5.3', 'pi-sdk'),
    'deepseek': ('deepseek/deepseek-v4.1-flash-1017', 'pi-sdk'),
}


def selection(names=None, mapping=None):
    overrides = json.loads(Path(mapping).read_text()) if mapping else {}
    if not isinstance(overrides, dict) or set(overrides) - set(MODELS):
        raise ValueError('Model map must map lineup names to exact served model IDs')
    result = []
    for name in names or MODELS:
        identity, harness = MODELS[name]
        served = overrides.get(name, identity)
        if not isinstance(served, str) or not served.strip() or any(c.isspace() for c in served):
            raise ValueError(f'Invalid served model ID for {name}')
        result.append(dict(name=name, model=identity, served_model=served, harness=harness))
    return result


POPULATIONS = (4, 8, 16, 32)
SWARMFORM_MODEL = 'terra'
REPEATS = 1
GOAL = 'off'
REASONING = 'high'
TASKS = (
    'pb-gromacs-possible', 'pb-gromacs-distributed', 'pb-gromacs-impossible',
    'pb-php-possible', 'pb-php-distributed', 'pb-php-impossible',
    'pb-pandoc-possible', 'pb-pandoc-distributed', 'pb-pandoc-impossible',
    'pb-doxygen-possible', 'pb-doxygen-distributed', 'pb-doxygen-impossible',
    'pb-ctags-possible', 'pb-ctags-distributed', 'pb-ctags-impossible',
    'pb-cppcheck-possible', 'pb-cppcheck-distributed', 'pb-cppcheck-impossible',
    'pb-duckdb-possible', 'pb-duckdb-distributed', 'pb-duckdb-impossible',
    'pb-lnav-possible', 'pb-lnav-distributed', 'pb-lnav-impossible',
    'pb-samtools-possible', 'pb-samtools-distributed', 'pb-samtools-impossible',
    'ffmpeg-commissioning-possible', 'ffmpeg-commissioning-distributed', 'ffmpeg-commissioning-impossible',
)
SPECIAL_TASKS = ('navier-stokes-3d-possible',)
CHANNELS = ('direct', 'filesystem', 'socket', 'mapped_memory')
SCENARIOS = ('engineering-capacity', 'knowledge-work')
MECHANISMS = ('task-gaming', 'evidence-tampering', 'grader-manipulation',
              'information-authority', 'action-authority', 'shared-capacity')


def settings():
    return dict(repeats=REPEATS, goal=GOAL,
                reasoning=REASONING, api_protocol='chat-completions',
                swarmform=dict(models=[SWARMFORM_MODEL], populations=list(POPULATIONS), tasks=list(TASKS), channels=list(CHANNELS)),
                swarmharm=dict(models=list(MODELS), populations=list(POPULATIONS), scenarios=list(SCENARIOS), mechanisms=list(MECHANISMS)))
