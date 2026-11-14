"""Common native-session construction for both studies and the N-agent API check."""
from copy import deepcopy
from pathlib import Path
from api_transport import ChatBridge
import claude_agent
import codex_agent
import codex_gateway
import pi_agent


def runtime(kind):
    return {'codex': codex_agent, 'claude-code': claude_agent, 'pi-sdk': pi_agent}[kind]


def registration(kind, model, base, goal='off'):
    if kind == 'codex':
        return codex_gateway.harness_registration(goal, model, api_base=base)
    if kind == 'claude-code':
        return claude_agent.gateway_registration(model, goal, api_base=base)
    return pi_agent.harness_registration(goal)


def create(kind, actor, events, *, api_protocol='chat-completions', served_model=None, **kwargs):
    bridge = None
    if api_protocol == 'chat-completions':
        bridge = ChatBridge(kwargs['api_base'], kwargs['api_key'], kwargs['model'],
                            Path(kwargs['folder']) / 'transport', served_model=served_model,
                            timeout=kwargs['request_timeout_ms'] / 1000)
        kwargs = {**kwargs, 'api_base': bridge.base, 'api_key': bridge.token}
        if kwargs.get('registered_harness'):
            kwargs['registered_harness'] = deepcopy(kwargs['registered_harness'])
            kwargs['registered_harness']['gateway'] = bridge.base
    elif api_protocol != 'native':
        raise ValueError('Unknown upstream API protocol')
    elif served_model and served_model != kwargs['model']:
        raise ValueError('Model ID mapping requires the Chat Completions transport')
    cls = {'codex': codex_agent.CodexAgent, 'claude-code': claude_agent.ClaudeAgent,
           'pi-sdk': pi_agent.PiAgent}[kind]
    try:
        agent = cls(actor, events, **kwargs)
    except BaseException:
        if bridge: bridge.close()
        raise
    if bridge:
        original_close = agent.close
        def close(*args, **options):
            try: return original_close(*args, **options)
            finally: bridge.close()
        agent.close = close
    return agent
