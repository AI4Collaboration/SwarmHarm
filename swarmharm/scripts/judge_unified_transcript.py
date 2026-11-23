#!/usr/bin/env python3
"""Run the blinded semantic judge through AxonHub and join both monitors."""
import argparse
from datetime import datetime, timezone
import json
from hashlib import sha256
from io import BytesIO
import re
import uuid
import urllib.error
from pathlib import Path
import sys
import urllib.request


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "swarmharm"))
sys.path.insert(0, str(REPO / "shared"))
from phase2 import claim_evidence
import guardrails


AXONHUB_RESPONSES = "https://lmportal.iefbr14.xyz/v1/responses"


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Refusing to replace {path}")
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


MAX_ERROR_BYTES = 32768
MAX_STREAM_BYTES = 64 * 1024 * 1024
KNOWN_ERROR_CODES = frozenset({
    'authentication_error', 'bad_gateway', 'content_filter', 'content_policy_violation',
    'context_length_exceeded', 'insufficient_quota', 'internal_server_error',
    'invalid_request_error', 'model_not_found', 'permission_denied', 'provider_error',
    'rate_limit_exceeded', 'rate_limit_error', 'server_error', 'timeout',
    'upstream_unavailable', 'upstream_timeout', 'service_unavailable',
})


# Fixed classifier only; original provider text never leaves memory. A lack of
# a match is unknown, not evidence that the provider did not refuse.
POLICY_REFUSAL_CODES=frozenset({'content_filter','content_policy_violation'})
POLICY_WORD=r'(?:content|safety|usage)[ -]?(?:policy|policies|guidelines)|moderation'
# Match only direct, complete statements about the current request. Unknown
# or longer free-form explanations remain unknown rather than guessed.
CURRENT_SUBJECT=r'(?:(?:this|your|current|the)\s+)?(?:request|prompt|response|output|completion|generation|message)'
POLICY_CAUSE=r'(?:(?:our|the|a)\s+)?(?:'+POLICY_WORD+r')(?:\s+(?:violation|violations|enforcement))?'
CURRENT_REFUSAL=re.compile(r'(?i)^\s*'+CURRENT_SUBJECT+r'\s+(?:'
    r'(?:violates|violated)\s+'+POLICY_CAUSE+r'|'
    r'(?:(?:was|is|has been|had been)\s+)?(?:blocked|rejected|refused|filtered)\s+'
    r'(?:by|due to|because of|for violating)\s+'+POLICY_CAUSE+r')\s*[.!?]?\s*$')
NEGATION=re.compile(r'(?i)\b(?:not|never|without|no|isn\'t|wasn\'t|aren\'t|didn\'t)\b')
HYPOTHETICAL=re.compile(r'(?i)\b(?:if|may|might|could|whether|example|hypothetical)\b')
HISTORICAL=re.compile(r'(?i)\b(?:previous|prior|earlier|past|historical|another|other)\b')


def completed_response_refusal(value):
    """Only the standard assistant message/content refusal shape counts."""
    if not isinstance(value,dict) or value.get('status')!='completed':return False
    output=value.get('output')
    if not isinstance(output,list):return False
    for message in output:
        if not isinstance(message,dict) or message.get('type')!='message' or message.get('role')!='assistant':continue
        content=message.get('content')
        if not isinstance(content,list):continue
        if any(isinstance(part,dict) and part.get('type')=='refusal' and isinstance(part.get('refusal'),str)
               for part in content):return True
    return False


def provider_error_facts(value,secret=''):
    """Inspect only the current error and the documented incomplete reason."""
    codes=set(); refused=False
    if isinstance(value,dict):
        if value.get('type')=='response.incomplete':
            response=value.get('response')
            details=response.get('incomplete_details') if isinstance(response,dict) else None
            reason=details.get('reason') if isinstance(details,dict) else None
            if reason=='content_filter' and reason!=secret:
                codes.add(reason);refused=True
            current=response.get('error') if isinstance(response,dict) else None
        elif value.get('type')=='response.failed':
            response=value.get('response')
            current=response.get('error') if isinstance(response,dict) else None
            if current is None:current=value.get('error')
        else:
            current=value.get('error',value)
    else:current=value
    messages=[]
    if isinstance(current,dict):
        for key in ('code','type','status'):
            item=current.get(key)
            if isinstance(item,str) and item!=secret and item in KNOWN_ERROR_CODES:
                codes.add(item)
                if key in ('code','type') and item in POLICY_REFUSAL_CODES:refused=True
        for key in ('message','detail','reason'):
            item=current.get(key)
            if isinstance(item,str) and item!=secret:messages.append(item)
    elif isinstance(current,str) and current!=secret:
        if current in KNOWN_ERROR_CODES:
            codes.add(current)
            if current in POLICY_REFUSAL_CODES:refused=True
        else:messages.append(current)
    # Messages are matched sentence by sentence, so reports of previous requests
    # and nested metadata cannot be attributed to the current request.
    for message in messages:
        for sentence in re.split(r'(?<=[.!?;])\s+|[\r\n]+',message):
            if (CURRENT_REFUSAL.search(sentence) and not HISTORICAL.search(sentence)
                    and not NEGATION.search(sentence) and not HYPOTHETICAL.search(sentence)):
                refused=True
    return codes, 'provider_stated_refusal' if refused else 'unknown'


STREAM_STATES = frozenset({'too_large','invalid_event','failed','incomplete','error',
                           'no_completion','nonstream_incomplete','interrupted','refusal'})


class StreamFailure(RuntimeError):
    """No provider-controlled text is included in this exception."""
    def __init__(self, state, data, policy_status='unknown'):
        super().__init__('Semantic judge stream did not complete')
        self.state=state if state in STREAM_STATES else 'error'
        self.policy_status=policy_status if policy_status=='provider_stated_refusal' else 'unknown'
        self.byte_count=len(data)
        self.digest=sha256(data).hexdigest()


def read_stream(response, capture, secret=''):
    """Write raw SSE only after completion; failed streams remain in memory."""
    data=[]; terminal=None; received=bytearray()
    try:
        for line in response:
            received.extend(line)
            if len(received)>MAX_STREAM_BYTES:
                raise StreamFailure('too_large',received[:MAX_STREAM_BYTES])
            if line.strip():
                if line.startswith(b'data:'):data.append(line[5:].strip())
                continue
            if not data:continue
            raw=b'\n'.join(data);data=[]
            if raw==b'[DONE]':break
            try:event=json.loads(raw)
            except (UnicodeDecodeError,json.JSONDecodeError):raise StreamFailure('invalid_event',received) from None
            if not isinstance(event,dict):raise StreamFailure('invalid_event',received)
            kind=event.get('type')
            if kind=='response.completed':terminal=event.get('response')
            elif kind in ('response.failed','response.incomplete','error'):
                raise StreamFailure({'response.failed':'failed','response.incomplete':'incomplete','error':'error'}[kind],received,provider_error_facts(event,secret)[1])
    except StreamFailure:
        raise
    except Exception:
        raise StreamFailure('interrupted',received) from None
    if not isinstance(terminal,dict) or terminal.get('status')!='completed':
        raise StreamFailure('no_completion',received,provider_error_facts(terminal,secret)[1])
    capture.write(received);capture.flush()
    return terminal


def http_status(exc):
    value=exc.code
    return value if type(value) is int and 100<=value<=599 else 0


def provider_http_diagnostic(exc, secret=''):
    """Store bounded hashes and enumerated categories; never store request IDs."""
    raw=exc.read(MAX_ERROR_BYTES+1)
    if not isinstance(raw,bytes):raise TypeError('HTTP body is not bytes')
    truncated=len(raw)>MAX_ERROR_BYTES;body=raw[:MAX_ERROR_BYTES]
    try:
        parsed=json.loads(body.decode('utf-8'));format_name='json'
    except (UnicodeDecodeError,json.JSONDecodeError):
        parsed=body.decode('utf-8',errors='replace');format_name='other'
    categories,policy_status=provider_error_facts(parsed,secret)
    if secret:categories.discard(secret)
    request_id_sha256=None
    value=exc.headers.get('X-Request-Id') if exc.headers is not None else None
    if isinstance(value,str):
        try:
            candidate=uuid.UUID(value)
            if (str(candidate)==value and candidate.version==4 and candidate.variant==uuid.RFC_4122
                    and (not secret or (value not in secret and secret not in value))):request_id_sha256=sha256(value.encode()).hexdigest()
        except ValueError:pass
    return {'status':http_status(exc),'body_format':format_name,'body_prefix_sha256':sha256(body).hexdigest(),
            'body_prefix_bytes':len(body),'body_truncated':truncated,
            'error_categories':sorted(categories),'policy_status':policy_status,
            'request_id_present':value is not None,'request_id_sha256':request_id_sha256}


def chat_completions_request(request_value):
    messages = [
        {"role": item["role"], "content": "\n".join(c["text"] for c in item["content"])}
        for item in request_value["input"]
    ]
    fmt = request_value["text"]["format"]
    payload = {
        "model": request_value["model"],
        "messages": messages,
        "response_format": {
            "type": "json_schema",
            "json_schema": {k: fmt[k] for k in ("name", "strict", "schema")},
        },
        "stream": False,
    }
    effort = (request_value.get("reasoning") or {}).get("effort")
    if effort:
        payload["reasoning_effort"] = effort
    return payload


def normalize_chat_completion(value):
    if not isinstance(value, dict):
        return value
    choices = value.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        return {"status": "failed", "error": value.get("error")}
    choice = choices[0]
    msg = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    finish = choice.get("finish_reason")
    if finish == "content_filter":
        return {"type": "response.incomplete", "status": "incomplete", "response": {"incomplete_details": {"reason": "content_filter"}}}
    if isinstance(msg.get("refusal"), str) and msg["refusal"]:
        parts = [{"type": "refusal", "refusal": msg["refusal"]}]
    elif finish == "stop" and isinstance(msg.get("content"), str):
        parts = [{"type": "output_text", "text": msg["content"]}]
    else:
        return {"status": "failed", "finish_reason": finish}
    return {
        "id": value.get("id"),
        "model": value.get("model"),
        "status": "completed",
        "usage": value.get("usage"),
        "output": [{"type": "message", "role": "assistant", "content": parts}],
    }


def post(request_value, key, stream_capture, api_base=None, protocol="responses"):
    if protocol == "chat-completions":
        base = guardrails.api_base_url(api_base) if api_base else AXONHUB_RESPONSES.removesuffix("/responses")
        url = base + "/chat/completions"
        payload = chat_completions_request(request_value)
    else:
        url = guardrails.api_base_url(api_base)+'/responses' if api_base else AXONHUB_RESPONSES
        payload = request_value
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "User-Agent": "swarmharm-transcript-judge/1.0",
        },
        method="POST",
    )
    with guardrails.open_url(request, timeout=300) as response:
        if protocol != "chat-completions" and 'text/event-stream' in response.headers.get('Content-Type', ''):
            return read_stream(response, stream_capture, key)
        value=json.load(response)
        if protocol == "chat-completions":
            value = normalize_chat_completion(value)
        if not isinstance(value,dict) or value.get('status')!='completed':
            raise StreamFailure('nonstream_incomplete',json.dumps(value,ensure_ascii=False).encode(),provider_error_facts(value,key)[1])
        return value


def next_attempt(root):
    directory = root / "transcript-judge-attempts"
    directory.mkdir(exist_ok=True)
    existing = [
        int(path.name.split("-", 1)[0])
        for path in directory.glob("[0-9][0-9][0-9][0-9]-request.json")
    ]
    number = max(existing, default=0) + 1
    return directory, f"{number:04d}"


def citation_events(judgment, mechanical=None):
    """Find explicit citations and causal actions needed to resolve ATIF-only citations."""
    citations = judgment['registered_claim_support']['citations'] + [
        row for finding in judgment['findings'].values() for row in finding['citations']]
    wanted = {row['world_event'] for row in citations if row['world_event'] is not None}
    return wanted


def reconstruct_citation_bindings(root, packet, judgment, mechanical):
    """Reconstruct the native evidence used by individual citations."""
    from phase2 import communication_evidence
    root = Path(root)
    world = json.loads((root / 'natural/world.json').read_text())
    wanted = citation_events(judgment, mechanical)
    bindings = list(communication_evidence.bind_events(
        root, world, packet['actors'], wanted, refresh_atif=False).values())
    return bindings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--review-dir",
        type=Path,
        help="Read and write monitor artifacts here while preserving the raw output.",
    )
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--model", default=claim_evidence.DEFAULT_JUDGE_MODEL)
    parser.add_argument("--api-base", help="Judge API base; defaults to the rollout's recorded endpoint")
    parser.add_argument(
        "--api-protocol",
        choices=("responses", "chat-completions"),
        default="responses",
        help="Transport protocol for the judge request (default: responses)",
    )
    parser.add_argument(
        "--response-file",
        type=Path,
        help="Validate a preserved response instead of making a model call.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Maximum attempts on transient HTTP or stream failures (default: 3).",
    )
    args = parser.parse_args(argv)
    if args.max_attempts < 1:
        parser.error("--max-attempts must be positive")
    root = guardrails.outside_repository(args.output, REPO, "Rollout output")
    review_root = (
        guardrails.outside_repository(args.review_dir, REPO, "Monitor review")
        if args.review_dir else root
    )
    packet_path = review_root / "transcript-judge-input.json"
    action_path = review_root / "action-monitor.json"
    if not packet_path.is_file() or not action_path.is_file():
        parser.error("Run the frozen independent review before semantic judging")
    packet = json.loads(packet_path.read_text())
    action = json.loads(action_path.read_text())
    mechanism_path = review_root / 'mechanism-review.json'
    mechanical_bytes = mechanism_path.read_bytes() if mechanism_path.is_file() else None
    mechanical = json.loads(mechanical_bytes) if mechanical_bytes is not None else None
    request_value = {**claim_evidence.judge_request(packet, args.model), 'stream': True}
    retryable_http = frozenset({408, 409, 425, 429, 500, 502, 503, 504} | set(range(520, 531)))
    limit = 1 if args.response_file else args.max_attempts
    response = None
    attempts = attempt = attempt_response = None
    stream_capture = BytesIO()
    for try_idx in range(1, limit + 1):
        attempts, attempt = next_attempt(review_root)
        attempt_request = attempts / f"{attempt}-request.json"
        attempt_response = attempts / f"{attempt}-response.json"
        write_new(attempt_request, request_value)
        secret = ''
        stream_capture = BytesIO()
        try:
            if args.response_file:
                response = json.loads(args.response_file.read_text())
            else:
                key_file = guardrails.credential_file(args.key_file, REPO)
                secret = key_file.read_text().strip()
                api_base = args.api_base or json.loads((root/'registration.json').read_text()).get(
                    'api_base', AXONHUB_RESPONSES.removesuffix('/responses'))
                write_new(attempts / f"{attempt}-route.json",
                          {'api_base': guardrails.api_base_url(api_base), 'model': args.model,
                           'api_protocol': args.api_protocol})
                post_kwargs = {}
                if api_base != AXONHUB_RESPONSES.removesuffix('/responses'):
                    post_kwargs['api_base'] = api_base
                if args.api_protocol != 'responses':
                    post_kwargs['protocol'] = args.api_protocol
                response = post(request_value, secret, stream_capture, **post_kwargs)
            if completed_response_refusal(response):
                data=stream_capture.getvalue() or json.dumps(response,ensure_ascii=False).encode()
                raise StreamFailure('refusal',data,'provider_stated_refusal')
            break
        except urllib.error.HTTPError as exc:
            status_code = http_status(exc)
            try:
                diagnostic=provider_http_diagnostic(exc,secret)
            except Exception:
                diagnostic={'status':status_code,'capture_state':'unavailable'}
            write_new(attempts / f"{attempt}-error.json",{
                'at':datetime.now(timezone.utc).isoformat(),'error_type':'HTTPError',
                'error':f'HTTP Error {status_code}', 'provider_response':diagnostic})
            if (status_code in retryable_http
                    and diagnostic.get('policy_status') != 'provider_stated_refusal'
                    and try_idx < limit):
                __import__('time').sleep(min(20.0, 2.0 * (2 ** (try_idx - 1))))
                continue
            raise RuntimeError(f'HTTP Error {status_code}; provider metadata saved.') from None
        except StreamFailure as exc:
            write_new(attempts / f"{attempt}-error.json",{
                'at':datetime.now(timezone.utc).isoformat(),'error_type':'StreamFailure',
                'stream_state':exc.state,'policy_status':exc.policy_status,
                'stream_prefix_sha256':exc.digest,'stream_prefix_bytes':exc.byte_count})
            if exc.policy_status != 'provider_stated_refusal' and try_idx < limit:
                __import__('time').sleep(min(20.0, 2.0 * (2 ** (try_idx - 1))))
                continue
            raise RuntimeError('Semantic judge stream did not complete; diagnostic saved.') from None
        except Exception as exc:
            write_new(attempts / f"{attempt}-error.json",{
                'at':datetime.now(timezone.utc).isoformat(),'error_type':'OtherError',
                'error':'diagnostic_unavailable'})
            if isinstance(exc, (TimeoutError, urllib.error.URLError, ConnectionError)) and try_idx < limit:
                __import__('time').sleep(min(20.0, 2.0 * (2 ** (try_idx - 1))))
                continue
            raise RuntimeError('Semantic judge failed; diagnostic saved.') from None
    response_bytes=(json.dumps(response,indent=2,ensure_ascii=False)+'\n').encode('utf-8')
    stage='model_identity'
    try:
        if response.get("model") != args.model:
            raise ValueError("Transcript judge returned a different model identity")
        stage='response_parse'
        judgment = json.loads(claim_evidence.response_text(response))
        stage='citation_binding'
        bindings = reconstruct_citation_bindings(root, packet, judgment, mechanical)
        stage='semantic_judgment'
        result = claim_evidence.transcript_judgment(
            packet,
            judgment,
            model=args.model,
            response_sha256=sha256(response_bytes).hexdigest(),
            native_action_bindings=bindings,
        )
        stage='mechanism_gate'
        if mechanical is not None:
            from phase2 import mechanism_review
            verdict = mechanism_review.complete_semantic_review(
                mechanical, packet, result, native_action_bindings=bindings)
            verdict_name = 'mechanism-verdict.json'
            summary = {'claim': verdict['mechanism'], 'passed': verdict['target_observed']}
        else:
            verdict = claim_evidence.claim_verdict(action, result)
            verdict_name = "claim-verdict.json"
            summary = {"claim": verdict["registered_claim"], "passed": verdict["passed"]}
    except Exception:
        stream_bytes=stream_capture.getvalue()
        write_new(attempts / f"{attempt}-validation-error.json",{
            'at':datetime.now(timezone.utc).isoformat(),'error_type':'ValidationError',
            'validation_stage':stage,'response_sha256':sha256(response_bytes).hexdigest(),
            'stream_sha256':sha256(stream_bytes).hexdigest(),'stream_bytes':len(stream_bytes)})
        raise RuntimeError('Semantic judge validation failed; diagnostic saved.') from None
    write_new(attempt_response,response)
    stream_bytes=stream_capture.getvalue()
    if stream_bytes:
        stream_path=attempts / f"{attempt}-stream.sse"
        with stream_path.open('xb') as capture:capture.write(stream_bytes)
    write_new(attempts / f"{attempt}-citation-bindings.json",bindings)
    write_new(review_root / "transcript-judge-request.json", request_value)
    write_new(review_root / "transcript-judge-response.json", response)
    write_new(review_root / "transcript-judge.json", result)
    write_new(review_root / verdict_name, verdict)
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
