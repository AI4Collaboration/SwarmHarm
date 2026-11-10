"""Render supplied participant inputs only; no experiment registration or execution."""
import json
from pathlib import Path

from swarmform import sustained_research as research
from swarmform.publication_updates import PublicationUpdates
from swarmform.structure import build_theory, verify_theory_inputs


def preview(*, responsive=False, context_maintenance=False):
    from codex_context import POLICY
    responsive = responsive or context_maintenance
    result = {'kind': 'unregistered-input-preview', 'model_calls': 0,
              'scope': 'Exact study-supplied inputs. Native harness stock instructions are unchanged and recorded separately at collection.',
              'model': 'openai/gpt-6.1-sol', 'reasoning': 'high', 'population': 8,
              'policy': research.policy(responsive=responsive), 'conditions': {},
              'automatic_notices': {'research_continuation': research.CONTINUATION,
                  'invalid_status_suffix': research.STATUS_ERROR,
                  'file_change_example': PublicationUpdates.notice([{'path': '/var/tmp/exports/navier-stokes/research.md'}])}}
    for condition in ('intended', 'unintended'):
        visible, truth, manifest = build_theory('sustained-review-v1', 8, condition,
                                              sustained_research=True, responsive_research=responsive)
        verification = verify_theory_inputs(visible, truth, sustained_research=True)
        if not verification['passed']:
            raise ValueError('Preview input verification failed')
        result['conditions'][condition] = {'input': visible, 'manifest': manifest, 'verification': verification}
    if context_maintenance:result['context_policy'] = dict(POLICY)
    intended = result['conditions']['intended']['input']
    unintended = result['conditions']['unintended']['input']
    for actor in intended['startup']:
        for path in ('/workspace/task.md', '/workspace/problem-provenance.txt', '/workspace/research-session.md'):
            if intended['startup'][actor][path] != unintended['startup'][actor][path]:
                raise ValueError('Unmatched I/U input')
    return result


def render_text(value):
    parts = ['UNREGISTERED REVIEW COPY — NO ROLLOUT', value['scope'],
             'Matched runtime policy:\n'+json.dumps(value['policy'], indent=2)]
    if value.get('context_policy'):
        parts.append('Matched context maintenance (no participant text):\n'+json.dumps(value['context_policy'],indent=2))
    for condition, item in value['conditions'].items():
        visible = item['input']; actor = 'Research01'
        parts.append('\nCONDITION: '+condition+' — startup texts (identical for all eight)')
        parts.extend(visible['prompts'][actor])
        for path, text in visible['startup'][actor].items():
            parts.append('\nFILE: '+path+'\n'+text)
        if condition == 'intended':
            parts.append('The other seven interfaces differ only in "Your address"; all exact inputs are in the accompanying JSON.')
        parts.append('TOOLS:\n'+json.dumps(visible['tools'], indent=2))
    parts.append('\nAUTOMATIC NOTICES:\n'+json.dumps(value['automatic_notices'], indent=2))
    return '\n\n'.join(parts)+'\n'


def write_preview(output, *, responsive=False, context_maintenance=False):
    output = Path(output)
    value = preview(responsive=responsive, context_maintenance=context_maintenance)
    output.mkdir(parents=True, exist_ok=True)
    (output/'agent-inputs.json').write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    (output/'agent-prompts.txt').write_text(render_text(value))
    return {'preview': str(output), 'files': ['agent-inputs.json', 'agent-prompts.txt'],
            'model_calls': 0, 'registration_created': False}
