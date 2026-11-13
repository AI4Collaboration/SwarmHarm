#!/usr/bin/env python3
"""Run the blinded semantic judge through AxonHub and join both monitors."""
import argparse
from datetime import datetime, timezone
import json
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


def read_stream(response, capture):
    """Retain the observer response stream; only a complete response is scoreable."""
    data = []
    terminal = None
    for line in response:
        capture.write(line)
        capture.flush()
        if line.strip():
            if line.startswith(b'data:'):
                data.append(line[5:].strip())
            continue
        if not data:
            continue
        raw = b'\n'.join(data)
        data = []
        if raw == b'[DONE]':
            break
        event = json.loads(raw)
        kind = event.get('type')
        if kind == 'response.completed':
            terminal = event['response']
        elif kind in ('response.failed', 'response.incomplete', 'error'):
            raise RuntimeError('Semantic judge stream ended with ' + kind)
    if terminal is None or terminal.get('status') != 'completed':
        raise RuntimeError('Semantic judge stream has no completed response')
    return terminal


def post(request_value, key, stream_path):
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
            with stream_path.open('xb') as capture:
                return read_stream(response, capture)
        return json.load(response)


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
        wanted.update(mechanism_review.fx_causal_releases(mechanical))
    return wanted


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
    request_value = {**claim_evidence.judge_request(packet, args.model), 'stream': True}
    attempts, attempt = next_attempt(review_root)
    attempt_request = attempts / f"{attempt}-request.json"
    attempt_response = attempts / f"{attempt}-response.json"
    write_new(attempt_request, request_value)
    try:
        if args.response_file:
            response = json.loads(args.response_file.read_text())
        else:
            key_file = guardrails.credential_file(args.key_file, REPO)
            response = post(request_value, key_file.read_text().strip(),
                            attempts / f"{attempt}-stream.sse")
        write_new(attempt_response, response)
    except Exception as exc:
        write_new(
            attempts / f"{attempt}-error.json",
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        raise
    try:
        if response.get("model") != args.model:
            raise ValueError("Transcript judge returned a different model identity")
        judgment = json.loads(claim_evidence.response_text(response))
        from phase2 import communication_evidence
        mechanism_path = review_root / 'mechanism-review.json'
        mechanical = json.loads(mechanism_path.read_text()) if mechanism_path.is_file() else None
        wanted = citation_events(judgment, mechanical)
        bindings = list(communication_evidence.bind_events(
            root, json.loads((root/'natural/world.json').read_text()), packet['actors'],
            wanted, refresh_atif=False).values())
        write_new(attempts / f"{attempt}-citation-bindings.json", bindings)
        result = claim_evidence.transcript_judgment(
            packet,
            judgment,
            model=args.model,
            response_sha256=claim_evidence.digest_file(attempt_response),
            native_action_bindings=bindings,
        )
        grid_path = review_root / "threat-grid-review.json"
        mechanism_path = review_root / 'mechanism-review.json'
        if mechanism_path.is_file():
            from phase2 import mechanism_review
            verdict = mechanism_review.complete_semantic_review(
                json.loads(mechanism_path.read_text()), packet, result, native_action_bindings=bindings)
            verdict_name = 'mechanism-verdict.json'
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
    except Exception as exc:
        write_new(
            attempts / f"{attempt}-validation-error.json",
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        raise
    write_new(review_root / "transcript-judge-request.json", request_value)
    write_new(review_root / "transcript-judge-response.json", response)
    write_new(review_root / "transcript-judge.json", result)
    write_new(review_root / verdict_name, verdict)
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
