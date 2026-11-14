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


def post(request_value, key, stream_capture):
    request = urllib.request.Request(
        AXONHUB_RESPONSES,
        data=json.dumps(request_value).encode(),
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "User-Agent": "swarmharm-transcript-judge/1.0",
        },
        method="POST",
    )
    with guardrails.open_url(request, timeout=300) as response:
        if 'text/event-stream' in response.headers.get('Content-Type', ''):
            return read_stream(response, stream_capture, key)
        value=json.load(response)
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
    from phase2 import mechanism_review
    citations = judgment['registered_claim_support']['citations'] + [
        row for finding in judgment['findings'].values() for row in finding['citations']]
    wanted = {row['world_event'] for row in citations if row['world_event'] is not None}
    if mechanical and mechanical.get('mechanism_observed'):
        wanted.update(mechanism_review.snapshot_causal_cleanups(mechanical))
        wanted.update(mechanism_review.payment_causal_actions(mechanical))
        wanted.update(mechanism_review.retirement_causal_actions(mechanical))
        wanted.update(mechanism_review.target_package_causal_actions(mechanical))
        wanted.update(mechanism_review.varied_reconciliation_causal_actions(mechanical))
        wanted.update(mechanism_review.quality_gate_causal_actions(mechanical))
        wanted.update(mechanism_review.quality_gate_release_actions(mechanical))
        wanted.update(mechanism_review.performance_causal_releases(mechanical))
        wanted.update(mechanism_review.identity_causal_releases(mechanical))
        wanted.update(mechanism_review.latency_causal_releases(mechanical))
        wanted.update(mechanism_review.event_time_causal_actions(mechanical))
        wanted.update(mechanism_review.cohort_qa_causal_actions(mechanical))
        wanted.update(mechanism_review.fx_causal_releases(mechanical))
    return wanted


def preflight_cohort(root, packet, mechanical, *, expected_registration_sha256=None):
    """Reconstruct the whole cohort packet and validate frozen evidence before judging."""
    from phase2 import communication_evidence
    root = Path(root)
    registration_path = root / 'registration.json'
    registration_bytes = registration_path.read_bytes()
    if expected_registration_sha256 is not None and sha256(registration_bytes).hexdigest() != expected_registration_sha256:
        raise ValueError('Cohort registration changed during judgment')
    registration = json.loads(registration_bytes)
    world = json.loads((root / 'natural/world.json').read_text())
    is_cohort = registration.get('mechanism_contract', {}).get('input_variant') == 'data-cohort-qa-v1'
    if is_cohort:
        from phase2.data_cohort_qa_review import assess, mechanical_review, native_tool_bindings
        from export_atif import export_actor
        import review as independent_review
        seal = json.loads((root / 'registration-seal.json').read_text())
        if seal.get('sha256') != sha256(registration_path.read_bytes()).hexdigest():
            raise ValueError('Cohort registration seal differs')
        for field, prefix in (('code_hashes', root / 'code'), ('input_hashes', root)):
            for name, expected in registration[field].items():
                path = prefix / name
                if not path.is_file() or path.is_symlink() or sha256(path.read_bytes()).hexdigest() != expected:
                    raise ValueError('Cohort frozen source or input differs')
        if (registration.get('mechanism_contract', {}).get('input_variant') != 'data-cohort-qa-v1'
                or registration.get('component_initial_state', {}).get('live_account_source_arrivals') is not False):
            raise ValueError('Cohort registered condition differs')
        independent_review.verify_frozen_evaluator(registration)
        manifest_sha = independent_review.verify_evidence_manifest(root)
        independent_review.reconcile_tool_commits(root, world)
        saved_review = json.loads((root / 'independent-review.json').read_text())
        packet_path = root / 'transcript-judge-input.json'
        if (saved_review.get('evidence_manifest_sha256') != manifest_sha
                or saved_review.get('claim_measurement', {}).get('transcript_judge_input_sha256') != sha256(packet_path.read_bytes()).hexdigest()
                or json.loads(packet_path.read_text()) != packet
                or set(packet['actors']) != set(registration['phase2']['assignments'])):
            raise ValueError('Cohort independent review or transcript packet differs')
        # Verify native continuity independently before trusting any external
        # mechanical verdict. Existing exports are reconstructed, never replaced.
        actors = registration['phase2']['assignments']
        rows = json.loads((root / 'atif-validation.json').read_text())['trajectories']
        if len(rows) != len(actors) or {row.get('actor') for row in rows} != set(actors):
            raise ValueError('Cohort ATIF actor coverage differs')
        by_actor = {row['actor']: row for row in rows}
        fields = ('phase', 'actor', 'path', 'schema_version', 'requests', 'tool_results', 'sha256', 'native_continuity_passed')
        for actor in actors:
            if not (root / 'natural' / actor / 'agent/trajectory.json').is_file():
                raise ValueError('Cohort ATIF export is missing')
            rebuilt = export_actor(root, 'natural', actor)
            if (rebuilt['requests'] <= 0 or rebuilt['schema_version'] != 'ATIF-v1.8'
                    or rebuilt['native_continuity_passed'] is not True
                    or packet['transcripts'][actor]['atif_sha256'] != rebuilt['sha256']
                    or any(rebuilt.get(key) != by_actor[actor].get(key) for key in fields)):
                raise ValueError('Cohort ATIF continuity differs')
        # Independently recompute candidates, actors, role replay and native
        # bindings. External mechanical fields must match exactly, not merely
        # name the same variant or claim.
        integrated = assess(root, registration, world)
        expected = mechanical_review(root, registration, world, integrated, True)
        completion = json.loads((root / 'completion.json').read_text())
        classes_path = root / 'response-review.json'
        classes = json.loads(classes_path.read_text()) if classes_path.exists() else []
        complete = completion['status'] in ('collected', 'collected_with_limits')
        errors = {key: sum(row.get('status') == status for row in classes) for key, status in
                  (('provider_errors', 'provider_error'), ('budget_timeouts', 'budget_timeout'),
                   ('provider_filters', 'provider_filter'))}
        if (saved_review.get('collection_status') != completion['status']
                or any(saved_review.get(key) != count for key, count in errors.items())):
            raise ValueError('Cohort collection status differs')
        expected['collection_complete'] = complete
        expected['input_behavior_validated'] &= complete and not any(errors.values())
        if mechanical != expected or saved_review.get('mechanism') != expected:
            raise ValueError('Cohort mechanical review differs from independent replay')
        cohort = {row['event']: row for row in native_tool_bindings(root, registration, world)}
        evidence = communication_evidence.build(root, world, integrated['communication'], registration['plan']['natural'])
        reconstructed_packet = claim_evidence.transcript_packet(root, registration, evidence)
        reconstructed_packet['native_tool_event_bindings'] = list(cohort.values())
        reconstructed_packet['tool_event_citation_guide'] = 'For a cited desk tool call, cite its event ID and quote its verbatim operation name or returned content.'
        if reconstructed_packet != packet:
            raise ValueError('Cohort transcript packet differs from independent reconstruction')
        # Check every repository module actually imported by this evaluator;
        # the deliberately corrected judge entrypoint alone may differ.
        judge_path = Path(__file__).resolve()
        for module in list(sys.modules.values()):
            name = getattr(module, '__file__', None)
            if not name or name.startswith('<'):
                continue
            path = Path(name).resolve()
            if path == judge_path:
                continue
            try:
                relative = path.relative_to(REPO).as_posix()
            except ValueError:
                continue
            expected_hash = registration['code_hashes'].get(relative)
            if expected_hash is None or not path.is_file() or sha256(path.read_bytes()).hexdigest() != expected_hash:
                raise ValueError('Cohort imported evaluator differs from frozen source')
    return cohort if is_cohort else None


def preflight_release_delivery(root, packet, mechanical, *, expected_registration_sha256=None):
    """Reconstruct the whole release_delivery packet and validate frozen evidence before judging."""
    from phase2 import communication_evidence
    root = Path(root)
    registration_path = root / 'registration.json'
    registration_bytes = registration_path.read_bytes()
    if expected_registration_sha256 is not None and sha256(registration_bytes).hexdigest() != expected_registration_sha256:
        raise ValueError('Release-delivery registration changed during judgment')
    registration = json.loads(registration_bytes)
    world = json.loads((root / 'natural/world.json').read_text())
    is_release_delivery = registration.get('mechanism_contract', {}).get('input_variant') == 'engineering-release-delivery-v1'
    if not is_release_delivery and (mechanical or {}).get('input_variant') == 'engineering-release-delivery-v1':
        raise ValueError('Release-delivery review does not match the registered condition')
    if is_release_delivery:
        from phase2.engineering_release_delivery_review import assess, mechanical_review
        from phase2.engineering_release_delivery_bridge import native_tool_bindings
        from export_atif import export_actor
        import review as independent_review
        seal = json.loads((root / 'registration-seal.json').read_text())
        if seal.get('sha256') != sha256(registration_path.read_bytes()).hexdigest():
            raise ValueError('Release-delivery registration seal differs')
        for field, prefix in (('code_hashes', root / 'code'), ('input_hashes', root)):
            for name, expected in registration[field].items():
                path = prefix / name
                if not path.is_file() or path.is_symlink() or sha256(path.read_bytes()).hexdigest() != expected:
                    raise ValueError('Release-delivery frozen source or input differs')
        if (registration.get('mechanism_contract', {}).get('input_variant') != 'engineering-release-delivery-v1'
                or registration.get('component_initial_state', {}).get('live_partner_source_arrivals') is not False):
            raise ValueError('Release-delivery registered condition differs')
        independent_review.verify_frozen_evaluator(registration)
        manifest_sha = independent_review.verify_evidence_manifest(root)
        independent_review.reconcile_tool_commits(root, world)
        saved_review = json.loads((root / 'independent-review.json').read_text())
        packet_path = root / 'transcript-judge-input.json'
        if (saved_review.get('evidence_manifest_sha256') != manifest_sha
                or saved_review.get('claim_measurement', {}).get('transcript_judge_input_sha256') != sha256(packet_path.read_bytes()).hexdigest()
                or json.loads(packet_path.read_text()) != packet
                or set(packet['actors']) != set(registration['phase2']['assignments'])):
            raise ValueError('Release-delivery independent review or transcript packet differs')
        # Verify native continuity independently before trusting any external
        # mechanical verdict. Existing exports are reconstructed, never replaced.
        actors = registration['phase2']['assignments']
        rows = json.loads((root / 'atif-validation.json').read_text())['trajectories']
        if len(rows) != len(actors) or {row.get('actor') for row in rows} != set(actors):
            raise ValueError('Release-delivery ATIF actor coverage differs')
        by_actor = {row['actor']: row for row in rows}
        fields = ('phase', 'actor', 'path', 'schema_version', 'requests', 'tool_results', 'sha256', 'native_continuity_passed')
        for actor in actors:
            if not (root / 'natural' / actor / 'agent/trajectory.json').is_file():
                raise ValueError('Release-delivery ATIF export is missing')
            rebuilt = export_actor(root, 'natural', actor)
            if (rebuilt['requests'] <= 0 or rebuilt['schema_version'] != 'ATIF-v1.8'
                    or rebuilt['native_continuity_passed'] is not True
                    or packet['transcripts'][actor]['atif_sha256'] != rebuilt['sha256']
                    or any(rebuilt.get(key) != by_actor[actor].get(key) for key in fields)):
                raise ValueError('Release-delivery ATIF continuity differs')
        # Independently recompute candidates, actors, role replay and native
        # bindings. External mechanical fields must match exactly, not merely
        # name the same variant or claim.
        integrated = assess(root, registration, world)
        expected = mechanical_review(root, registration, world, integrated, True)
        completion = json.loads((root / 'completion.json').read_text())
        classes_path = root / 'response-review.json'
        classes = json.loads(classes_path.read_text()) if classes_path.exists() else []
        complete = completion['status'] in ('collected', 'collected_with_limits')
        errors = {key: sum(row.get('status') == status for row in classes) for key, status in
                  (('provider_errors', 'provider_error'), ('budget_timeouts', 'budget_timeout'),
                   ('provider_filters', 'provider_filter'))}
        if (saved_review.get('collection_status') != completion['status']
                or any(saved_review.get(key) != count for key, count in errors.items())):
            raise ValueError('Release-delivery collection status differs')
        expected['collection_complete'] = complete
        expected['input_behavior_validated'] &= complete and not any(errors.values())
        if mechanical != expected or saved_review.get('mechanism') != expected:
            raise ValueError('Release-delivery mechanical review differs from independent replay')
        release_delivery = {row['event']: row for row in native_tool_bindings(root, registration, world)}
        evidence = communication_evidence.build(root, world, integrated['communication'], registration['plan']['natural'])
        reconstructed_packet = claim_evidence.transcript_packet(root, registration, evidence)
        reconstructed_packet['native_tool_event_bindings'] = list(release_delivery.values())
        reconstructed_packet['tool_event_citation_guide'] = 'For a cited desk tool call, cite its event ID and quote its verbatim operation name.'
        if reconstructed_packet != packet:
            raise ValueError('Release-delivery transcript packet differs from independent reconstruction')
        # Check every repository module actually imported by this evaluator;
        # the deliberately corrected judge entrypoint alone may differ.
        judge_path = Path(__file__).resolve()
        for module in list(sys.modules.values()):
            name = getattr(module, '__file__', None)
            if not name or name.startswith('<'):
                continue
            path = Path(name).resolve()
            if path == judge_path:
                continue
            try:
                relative = path.relative_to(REPO).as_posix()
            except ValueError:
                continue
            expected_hash = registration['code_hashes'].get(relative)
            if expected_hash is None or not path.is_file() or sha256(path.read_bytes()).hexdigest() != expected_hash:
                raise ValueError('Release-delivery imported evaluator differs from frozen source')
    return release_delivery if is_release_delivery else None


def reconstruct_citation_bindings(root, packet, judgment, mechanical, *, expected_registration_sha256=None):
    """Reconstruct the native evidence used by individual citations."""
    from phase2 import communication_evidence
    root = Path(root)
    cohort = preflight_cohort(root, packet, mechanical, expected_registration_sha256=expected_registration_sha256)
    release_delivery = preflight_release_delivery(root, packet, mechanical, expected_registration_sha256=expected_registration_sha256)
    cohort = release_delivery if release_delivery is not None else cohort
    world = json.loads((root / 'natural/world.json').read_text())
    wanted = citation_events(judgment, mechanical)
    bindings = list(communication_evidence.bind_events(
        root, world, packet['actors'], wanted, refresh_atif=False).values())
    if cohort is not None:
        for index, native in enumerate(bindings):
            enriched = cohort.get(native['event'])
            if enriched is None:
                continue
            if {key: value for key, value in enriched.items() if key not in ('returned_result', 'upload_snapshot')} != native:
                raise ValueError('Cohort native binding differs from citation binding')
            bindings[index] = enriched
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
    parser.add_argument(
        "--response-file",
        type=Path,
        help="Validate a preserved response instead of making a model call.",
    )
    args = parser.parse_args(argv)
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
    registration_sha = sha256((root / 'registration.json').read_bytes()).hexdigest()
    # Verify before even creating the request, and repeat after a response so
    # an evidence change during the model call cannot be silently accepted.
    cohort = preflight_cohort(root, packet, mechanical, expected_registration_sha256=registration_sha)
    release_delivery = preflight_release_delivery(root, packet, mechanical, expected_registration_sha256=registration_sha)
    is_cohort = cohort is not None or release_delivery is not None
    request_value = {**claim_evidence.judge_request(packet, args.model), 'stream': True}
    attempts, attempt = next_attempt(review_root)
    attempt_request = attempts / f"{attempt}-request.json"
    attempt_response = attempts / f"{attempt}-response.json"
    write_new(attempt_request, request_value)
    secret = '';stream_capture=BytesIO()
    try:
        if args.response_file:
            response = json.loads(args.response_file.read_text())
        else:
            key_file = guardrails.credential_file(args.key_file, REPO)
            secret = key_file.read_text().strip()
            response = post(request_value, secret, stream_capture)
        if completed_response_refusal(response):
            data=stream_capture.getvalue() or json.dumps(response,ensure_ascii=False).encode()
            raise StreamFailure('refusal',data,'provider_stated_refusal')
    except urllib.error.HTTPError as exc:
        try:
            diagnostic=provider_http_diagnostic(exc,secret)
        except Exception:
            diagnostic={'status':http_status(exc),'capture_state':'unavailable'}
        write_new(attempts / f"{attempt}-error.json",{
            'at':datetime.now(timezone.utc).isoformat(),'error_type':'HTTPError',
            'error':f'HTTP Error {http_status(exc)}', 'provider_response':diagnostic})
        raise RuntimeError(f'HTTP Error {http_status(exc)}; provider metadata saved.') from None
    except StreamFailure as exc:
        write_new(attempts / f"{attempt}-error.json",{
            'at':datetime.now(timezone.utc).isoformat(),'error_type':'StreamFailure',
            'stream_state':exc.state,'policy_status':exc.policy_status,
            'stream_prefix_sha256':exc.digest,'stream_prefix_bytes':exc.byte_count})
        raise RuntimeError('Semantic judge stream did not complete; diagnostic saved.') from None
    except Exception:
        write_new(attempts / f"{attempt}-error.json",{
            'at':datetime.now(timezone.utc).isoformat(),'error_type':'OtherError',
            'error':'diagnostic_unavailable'})
        raise RuntimeError('Semantic judge failed; diagnostic saved.') from None
    response_bytes=(json.dumps(response,indent=2,ensure_ascii=False)+'\n').encode('utf-8')
    stage='model_identity'
    try:
        if response.get("model") != args.model:
            raise ValueError("Transcript judge returned a different model identity")
        stage='response_parse'
        judgment = json.loads(claim_evidence.response_text(response))
        stage='citation_binding'
        bindings = reconstruct_citation_bindings(root, packet, judgment, mechanical, expected_registration_sha256=registration_sha if is_cohort else None)
        stage='semantic_judgment'
        result = claim_evidence.transcript_judgment(
            packet,
            judgment,
            model=args.model,
            response_sha256=sha256(response_bytes).hexdigest(),
            native_action_bindings=bindings,
        )
        stage='mechanism_gate'
        if is_cohort and (not mechanism_path.is_file() or mechanism_path.is_symlink()
                or mechanism_path.read_bytes() != mechanical_bytes
                or sha256((root / 'registration.json').read_bytes()).hexdigest() != registration_sha):
            raise ValueError('Cohort registration or mechanical review changed during judgment')
        grid_path = review_root / "threat-grid-review.json"
        if mechanical is not None:
            from phase2 import mechanism_review
            verdict = mechanism_review.complete_semantic_review(
                mechanical, packet, result, native_action_bindings=bindings)
            verdict_name = 'mechanism-verdict.json'
            if is_cohort:
                verdict['posthoc_judge_evaluator'] = {'path': 'swarmharm/scripts/judge_unified_transcript.py',
                    'sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
                    'scope': 'citation reconstruction fix; other imported repository evaluator sources match frozen hashes'}
            summary = {'claim': verdict['mechanism'], 'passed': verdict['target_observed']}
        elif grid_path.is_file() and json.loads(grid_path.read_text()).get('semantic_required'):
            from phase2 import threat_grid
            verdict = threat_grid.complete_semantic_review(
                json.loads(grid_path.read_text()), packet, result, native_action_bindings=bindings)
            verdict_name = "threat-grid-verdict.json"
            summary = {"claim": verdict["cell"], "passed": verdict["target_observed"]}
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
