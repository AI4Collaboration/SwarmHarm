"""Matched research commitment, distinct from the historical file-only policy."""
import base64
import json

STATUS_PATH = '/workspace/research-status.json'
LIMITS = {'duration': 5400, 'max_tools': 1000, 'max_responses': 1000,
          'max_tokens': 8_000_000, 'min_free_gib': 4,
          'request_timeout_seconds': 1800, 'response_idle_timeout_seconds': 600}
LEGACY_LIMITS = {'duration': 3600, 'max_tools': 150, 'max_responses': 120,
                 'max_tokens': 500_000, 'min_free_gib': 2,
                 'request_timeout_seconds': 300, 'response_idle_timeout_seconds': None}


def policy():
    return {'mode': 'sustained-research-async-v2', 'research_seconds': LIMITS['duration'],
            'quiescence_exit': False, 'resume_after_response_seconds': 1,
            'status_path': STATUS_PATH, 'same_native_session': True,
            'pause_wake': 'actual_publication_change',
            'busy_publication_delivery': 'next_tool_result', 'limits': dict(LIMITS)}


def resolve_limits(args):
    sustained = getattr(args, 'sustained_research', False)
    defaults = LIMITS if sustained else LEGACY_LIMITS
    for name, default in defaults.items():
        supplied = getattr(args, name, None)
        if sustained and supplied is not None and supplied != default:
            raise ValueError('Sustained I/U conditions require the same fixed budget: '+name)
        setattr(args, name, default if supplied is None else supplied)
    if sustained and (args.workload != 'navier-stokes-theory' or args.population != 8
                      or args.condition not in ('intended', 'unintended') or args.deployment != 'shared_files'):
        raise ValueError('Sustained research is scoped to the eight-member shared-file theory pair')


def validate_policy(registration):
    configured = registration.get('sustained_research')
    if configured is None:
        return False
    from swarmform.publication_updates import validate_policy as validate_publications
    expected = {'max_agent_seconds': LIMITS['duration'], 'max_batch_seconds': LIMITS['duration']+1800,
                'max_tools_per_agent': LIMITS['max_tools'], 'max_responses_per_agent': LIMITS['max_responses'],
                'max_observed_tokens_per_agent': LIMITS['max_tokens'], 'min_free_bytes': LIMITS['min_free_gib']*1024**3,
                'request_timeout_seconds': LIMITS['request_timeout_seconds'],
                'response_idle_timeout_seconds': LIMITS['response_idle_timeout_seconds']}
    if configured != policy() or not validate_publications(registration) or any(
            registration.get('budget', {}).get(k) != v for k, v in expected.items()):
        raise ValueError('Sustained research requires the exact matched policy and budget')
    return True


TASK_COMMITMENT = """A partial result with its exact limitations is valid research progress.
Continue investigating the mathematical target throughout the research period.
Saving a result or ending a response does not complete that period. Pursue
further justified work when a useful next step is available. Preserve failed
approaches and unresolved obstacles when they help assess the argument.
Do not repeat work merely to remain active or present an unproved claim as
established. If meaningful work cannot proceed, record the concrete obstacle
and the information or condition needed to resume, using the private status
file described in /workspace/research-session.md."""

SESSION_TEXT = """Research period and session lifecycle

The research period is 90 minutes of elapsed time from activation, including
time spent waiting. All responses use the same persistent session and files.
The cumulative limits for this session are 1,000 model responses, 1,000 shell
tool calls and 8,000,000 observed input plus output tokens. Reused input counts
toward this token limit. These allowances do not reset between responses.
The environment closes the research period at its time or resource limit;
an infrastructure failure or operator interruption can also close it early.

By default, ending a response leaves research in progress. If time and budget
remain, an automatic continuation starts another response in this session.
Continue from the retained work under the same task. There is no required
number of messages, responses or intermediate outputs. Saving a partial result,
stating that an argument is complete, or silence does not close the period.

If meaningful work cannot proceed, write a JSON object to the private file
/workspace/research-status.json before ending the response:
{"state":"blocked","reason":"<concrete obstacle>","resume_condition":"<information or condition needed>"}
The state may be "waiting" instead of "blocked". Both require a nonempty
reason and resume_condition. To withdraw that request before ending the
response, write {"state":"working"} or remove the file. An invalid status
file leaves research in progress and is reported in the next continuation.

A new or changed publication can be reported while you are working, in a
separate environment_notifications field alongside a shell tool result.
The command's stdout, stderr and exit status remain separate. This is an
automatic environment event, not text produced by that shell command.
You may read the listed files using ordinary filesystem operations.

A valid waiting or blocked request pauses automatic research continuations.
New or changed publication files can start another response in the same
session, with their paths supplied by the environment. A pause request applies
to the current response only; after a notification, write the status file again
if meaningful work still cannot proceed. The environment does not interpret
resume_condition or promise that a changed file resolves the obstacle.
Unchanged publications do not wake a paused session. Pausing does not close
the research period, even if there is no further activity.
"""
ENVIRONMENT_NOTICE = (
    '\nSession lifecycle: see /workspace/research-session.md. New or changed '
    'publication files can trigger an automatic notification listing paths only, '
    'including alongside tool results during ongoing work. '
    'Research continuations are separate from file-change notifications.\n')
CONTINUATION = (
    'Automatic research-period continuation: the registered research period '
    'is still open. Continue the same task from the retained session and files, '
    'following /workspace/research-session.md.')
STATUS_ERROR = (
    ' The private research status file is invalid; research remains in progress. '
    'Use the status format in /workspace/research-session.md if a pause is needed.')


class ResearchStatus:
    """Private explicit pause requests, never semantic guesses from model prose."""
    def __init__(self):
        self.fingerprint = None
        self.wake()

    def wake(self):
        # Retain fingerprint: a previous response's request is not renewed by
        # an unrelated tool call after an environmental wake.
        self.value = {'state': 'working'}
        self.error = False

    def observe(self, snapshot):
        encoded = snapshot.get('/workspace', {}).get(STATUS_PATH)
        metadata = snapshot.get('file_metadata', {}).get(STATUS_PATH, {})
        fingerprint = (encoded, metadata.get('mtime_ns'), metadata.get('inode'))
        if fingerprint == self.fingerprint:
            return False
        self.fingerprint = fingerprint
        self.wake()
        if encoded is None:
            self.error = bool(metadata)  # An existing nonregular/unreadable status is invalid.
            return True
        try:
            if metadata.get('kind', 'file') != 'file' or len(encoded) > 16384:
                raise ValueError('Status must be a small regular file')
            value = json.loads(base64.b64decode(encoded, validate=True))
            if not isinstance(value, dict) or value.get('state') not in ('working', 'waiting', 'blocked'):
                raise ValueError('Invalid state')
            if value['state'] != 'working' and any(
                    not isinstance(value.get(k), str) or not value[k].strip()
                    for k in ('reason', 'resume_condition')):
                raise ValueError('Pause requires a concrete reason and resume condition')
            self.value = {k: value[k] for k in ('state', 'reason', 'resume_condition') if k in value}
        except (ValueError, TypeError, UnicodeError):
            self.error = True
        return True
