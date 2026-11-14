"""Native harness participant using the same task, workstation and cohort stop."""
import asyncio
import json
from pathlib import Path
import queue
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'shared'))
import model_session


async def participate(cohort, actor, limits):
    args = cohort.args
    events = queue.Queue(); agent = None; calls = {}
    usage = cohort.usage[actor] = {'responses': 0, 'tools': 0, 'tokens': 0}
    try:
        tools = cohort.visible['tools']
        agent = model_session.create(args.harness, actor, events,
            folder=cohort.out / 'native' / actor, model=args.model, api_base=args.base_url,
            api_key=args._api_key, api_protocol=args.api_protocol, served_model=args.served_model,
            thinking_level='high', max_output_tokens=16384, context_window=1_000_000,
            request_timeout_ms=args.seconds*1000, tools=tools,
            active_tools=[t['name'] for t in tools], job_context=None, goal_mode='off')
        while not cohort.stopping.is_set():
            try: _, message = await asyncio.to_thread(events.get, True, .25)
            except queue.Empty: continue
            kind = message['type']; cohort.trace(actor, 'native_event', event=message)
            if kind == 'ready': agent.prompt(*cohort.visible['prompts'][actor])
            elif kind == 'provider_response':
                response = message.get('event', {}).get('response', {})
                if response.get('status') == 'failed': raise RuntimeError(str(response.get('error')))
                usage['responses'] += 1
                count = (response.get('usage') or {}).get('total_tokens', 0)
                usage['tokens'] += count
                for call in response.get('output', []):
                    if call.get('type') == 'function_call': calls[call['call_id']] = call
                if usage['tokens'] >= limits['tokens']:
                    cohort.stop('observed_token_budget'); return
            elif kind == 'tool_call':
                if usage['tools'] >= limits['tools']:
                    cohort.stop('tool_budget'); return
                usage['tools'] += 1
                call_id = message['call_id'].split('|')[0]
                call = calls[call_id]
                arguments = json.loads(call['arguments'])
                if call['name'] != 'bash' or not isinstance(arguments.get('command'), str):
                    result = {'error': 'Expected the bash tool with a string command'}
                else:
                    cohort.trace(actor, 'tool_start', call_id=call_id, command=arguments['command'])
                    task = asyncio.create_task(asyncio.to_thread(cohort.tool, actor, arguments['command'], call_id))
                    cohort.active_tools.add(task)
                    task.add_done_callback(lambda done, call_id=call_id: cohort.tool_completed(done, actor, call_id))
                    result, _ = await asyncio.shield(task)
                agent.reply(message['id'], output=json.dumps(result))
                if usage['responses'] >= limits['responses']:
                    cohort.stop('response_or_tool_budget'); return
            elif kind == 'settled':
                if message.get('error_message'): raise RuntimeError(message['error_message'])
                cohort.returns[actor] = 'model_finished'; return
            elif kind in ('fatal', 'exited', 'closed'):
                raise RuntimeError(str(message))
    except asyncio.CancelledError:
        cohort.trace(actor, 'cancelled', reason=cohort.reason)
        raise
    except Exception as error:
        cohort.errors[actor] = f'{type(error).__name__}: {error}'
        cohort.stop('participant_error')
    finally:
        if agent is not None: await asyncio.to_thread(agent.close)
