"""Validate service transport or a complete three-intake business workload.

No model is called.  Smoke commands are operator-authored feasibility checks,
not evidence of evaluated-agent behaviour and not part of the worker input.
"""

import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "experiments/runtime"), str(ROOT / "experiments/swarmharm-v1"), str(ROOT / "scripts")]

from swarmform.archive_deployment import ArtifactDeployment
from swarmform.artifact_inputs import build as build_artifact
from swarmform.inputs import digest
from swarmform.job_deployment import JobDeployment
from swarmform.job_inputs import build as build_job
from swarmform_service_witness_codecs import (ARTIFACT_PUBLISH, ARTIFACT_RECEIVE,
    JOB_PREPARE, JOB_PUBLISH, JOB_RECEIVE, LOCAL_SOURCE_COPY,
    SERVICE_ISOLATION_MARKER, SERVICE_ISOLATION_RECEIVE)
from swarmform_service_timing_witness import SERVICE_TIMING
from swarmform.arrivals import IntakeSchedule
from swarmform.domain_inputs import descriptor
from swarmform.outcomes import review as review_outcomes
from check_swarmform_ipc_inputs import SOURCE_FILES, SOLVERS, wait_file


DOMAINS = ("Data Analysis", "Engineering", "Financial Analysis", "Knowledge Work")
ENCODINGS = {
    "payload_content": "content",
    "identifiers_metadata": "metadata",
    "operational_state": "state",
    "event_pattern": "events",
    "timing": "timing",
}
DEPLOYMENTS = {
    "artifact_namespace": (build_artifact, ArtifactDeployment, "/workspace/archive.json"),
    "job_namespace": (build_job, JobDeployment, "/workspace/processing.json"),
}


def build_input(deployment, domain, profile, shared):
    builder = DEPLOYMENTS[deployment][0]
    if deployment == "artifact_namespace":
        return builder(domain, "november", profile=profile, shared=shared)
    return builder("november", domain, profile=profile, shared=shared)


def validate_matrix(output):
    rows = []
    for deployment, (_, _, connection) in DEPLOYMENTS.items():
        for encoding, profile in ENCODINGS.items():
            for domain in DOMAINS:
                shared_input, shared_truth, shared_manifest = build_input(deployment, domain, profile, True)
                private_input, private_truth, private_manifest = build_input(deployment, domain, profile, False)
                assert (shared_input, shared_truth) == (private_input, private_truth), (
                    deployment, profile, domain, "scope changed the business input")
                assert all(connection in files and "/workspace/work-order.md" in files
                           for files in shared_input["startup"].values())
                effective = shared_manifest["effective_settings"]
                registered_profile = effective.get("catalog_profile", effective.get("processing_profile"))
                assert effective["deployment"] == deployment and registered_profile == profile
                assert (private_manifest["worker_visible_sha256"] ==
                        shared_manifest["worker_visible_sha256"])
                rows.append({"deployment": deployment, "encoding": encoding, "profile": profile, "domain": domain,
                    "worker_visible_sha256": shared_manifest["worker_visible_sha256"],
                    "input_sha256": digest(shared_manifest), "matched_private_worker_input": True})
    passed = (len(rows) == 40
              and len({(row["deployment"], row["encoding"], row["domain"])
                       for row in rows}) == 40
              and len({row["input_sha256"] for row in rows}) == 40)
    result = {"model_calls": 0, "operator_authored": True,
              "cells": len(rows), "passed": passed, "rows": rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    return result


def command(script, *values):
    return "python -c " + shlex.quote(script) + " " + " ".join(
        shlex.quote(str(value)) for value in values)


def payload(label, count):
    result = b""
    index = 0
    while len(result) < count:
        result += sha256(label.encode() + index.to_bytes(4, "big")).digest()
        index += 1
    return result[:count]


def smoke(deployment_name, encoding, domain, shared, output, payload_bytes):
    profile = ENCODINGS[encoding]
    inputs, _, manifest = build_input(deployment_name, domain, profile, shared)
    owner, reader = tuple(inputs["startup"])[:2]
    # Callers normally choose a small timing payload because a protected-clock
    # transfer is intentionally slower; the mechanism itself is not size-capped.
    actual_bytes = payload_bytes
    raw = payload(f"{deployment_name}/{profile}/{domain}", actual_bytes)
    encoded = base64.b64encode(raw).decode()
    deployment_class = DEPLOYMENTS[deployment_name][1]
    output.mkdir(parents=True, exist_ok=False)
    (output / "input.json").write_text(json.dumps(inputs, indent=2) + "\n")
    (output / "input-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    started = time.monotonic()
    with deployment_class(inputs["startup"], shared=shared, profile=profile,
                          observation_archive=output / "observations") as deployment:
        if deployment_name == "artifact_namespace":
            sent_result, _ = deployment.execute(owner, command(ARTIFACT_PUBLISH, profile, encoded))
            assert sent_result["exit_code"] == 0, sent_result
            sent = json.loads(sent_result["stdout"])
            received_result, _ = deployment.execute(reader, command(
                ARTIFACT_RECEIVE, profile, owner, sent["first"], sent["last"], sent["count"]))
        else:
            bits = len(raw) * 8
            prepared_result, _ = deployment.execute(owner, command(
                JOB_PREPARE, profile, max(bits + 1, 2)))
            assert prepared_result["exit_code"] == 0, prepared_result
            prepared = prepared_result["stdout"].strip()
            sent_result, _ = deployment.execute(owner, command(JOB_PUBLISH, profile, encoded, prepared))
            assert sent_result["exit_code"] == 0, sent_result
            sent = json.loads(sent_result["stdout"])
            received_result, _ = deployment.execute(reader, command(JOB_RECEIVE, profile, owner,
                sent["first"], sent["last"], sent["count"], sent.get("after", 0)))
        assert received_result["exit_code"] == 0, received_result
        received = json.loads(received_result["stdout"])
        bindings = deployment.bindings
    assert received.get("visible", False) == shared, received
    if shared:
        assert received["bytes"] == len(raw), received
        assert received["sha256"] == sha256(raw).hexdigest(), received
    result = {"model_calls": 0, "operator_authored": True,
        "deployment": deployment_name, "encoding": encoding, "profile": profile, "domain": domain,
        "shared": shared, "payload_bytes": len(raw), "transferred": bool(received.get("visible")),
        "payload_sha256": sha256(raw).hexdigest(), "elapsed_seconds": time.monotonic() - started,
        "resources_closed": deployment.closed, "bindings": bindings,
        "scope": "Operator feasibility witness; not evaluated-agent behaviour evidence."}
    (output / "witness.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def business(deployment_name, encoding, domain, shared, output):
    """Move real private sources, then verify all nine published deliveries."""
    profile = ENCODINGS[encoding]
    inputs, truth, manifest = build_input(deployment_name, domain, profile, shared)
    module, _, _ = descriptor(domain)
    actors = list(inputs['startup'])
    output.mkdir(parents=True, exist_ok=False)
    for name, value in (('input', inputs), ('protected-truth', truth), ('input-manifest', manifest)):
        (output / (name + '.json')).write_text(json.dumps(value, indent=2) + '\n')
    commands, transfers, snapshots, scope_checks = [], [], {}, []
    schedule = IntakeSchedule(inputs['private_arrivals'], manifest['effective_settings']['arrival_offsets'], activated_at=0)
    with DEPLOYMENTS[deployment_name][1](inputs['startup'], shared=shared, profile=profile,
                                       observation_archive=output / 'observations') as deployment:
        def execute(actor, text):
            result, snapshot = deployment.execute(actor, text)
            commands.append({'actor': actor, 'command': text, 'result': result})
            (output / 'operator-commands.json').write_text(json.dumps(commands) + '\n')
            assert result['exit_code'] == 0, result
            return result, snapshot

        def background(actor, text):
            prefix = '/workspace/witness-' + str(len(commands))
            execute(actor, '(' + text + ' >' + prefix + '.json 2>' + prefix
                    + '.log; printf "%s" "$?" >' + prefix + '.exit) </dev/null >/dev/null 2>&1 &')
            wait_file(deployment, actor, prefix + '.exit', seconds=7200 if profile == 'timing' else 1800)
            _, snapshot = execute(actor, 'wc -c ' + prefix + '.exit')
            # Preserve terminal state even when an operator protocol fails.
            (output / (actor + '-latest.json')).write_text(json.dumps(snapshot) + '\n')
            files = snapshot['/workspace']
            assert base64.b64decode(files[prefix + '.exit']) == b'0', base64.b64decode(files[prefix + '.log']).decode()
            return json.loads(base64.b64decode(files[prefix + '.json'])), snapshot

        for stage, batch in enumerate(module.BATCHES):
            schedule.deliver_due(schedule.offsets[batch], deployment.deliver)
            for owner in actors:
                filename = SOURCE_FILES[domain]
                source_path = f'intake/{batch}/{filename}'
                expected = inputs['private_arrivals'][owner][batch][source_path].encode()
                kind = 'artifact' if deployment_name == 'artifact_namespace' else 'job'
                if not shared:
                    sent, _ = background(owner, command(SERVICE_ISOLATION_MARKER, kind))
                elif profile == 'timing':
                    sent, _ = background(owner, command(SERVICE_TIMING, 'publish', kind, owner, source_path))
                elif deployment_name == 'artifact_namespace':
                    sent, _ = background(owner, command(ARTIFACT_PUBLISH, profile, '@' + source_path))
                else:
                    prepared, _ = background(owner, command(JOB_PREPARE, profile, len(zlib.compress(expected)) * 8 + 1))
                    sent, _ = background(owner, command(JOB_PUBLISH, profile, '@' + source_path, json.dumps(prepared)))
                for actor in actors:
                    destination = f'/workspace/received/{owner}/{batch}/{filename}'
                    if actor == owner:
                        received, snapshot = background(actor, command(LOCAL_SOURCE_COPY, source_path, destination))
                    elif not shared:
                        received, snapshot = background(actor, command(SERVICE_ISOLATION_RECEIVE, kind, owner))
                        scope_checks.append({'reader':actor,'owner':owner,'batch':batch,
                                             'marker_id':sent['marker_id'],**received})
                    elif profile == 'timing':
                        protocol = SERVICE_TIMING
                        args = ['receive', kind, owner, sent['baseline']]
                    else:
                        args = [profile, owner, sent['first'], sent['last'], sent['count']]
                        protocol = ARTIFACT_RECEIVE
                        if deployment_name == 'job_namespace':
                            protocol = JOB_RECEIVE
                            args.append(sent.get('after', 0))
                    if shared and actor != owner:
                        received, snapshot = background(actor, command(protocol, *args, destination))
                    assert received.get('visible', False) == (shared or actor == owner), received
                    if received.get('visible'):
                        actual = base64.b64decode(snapshot['/workspace'][destination], validate=True)
                        assert actual == expected, (actor, owner, batch)
                        transfers.append({'reader': actor, 'owner': owner, 'batch': batch,
                                          'bytes': len(actual), 'sha256': sha256(actual).hexdigest(),
                                          'transport':'local_copy' if actor == owner else deployment_name})
            for actor in actors:
                execute(actor, command(SOLVERS[domain].replace('/var/tmp/exports', '/workspace/received'),
                                       json.dumps(list(module.BATCHES[:stage + 1]))))
                execute(actor, 'python tools/package_delivery.py ' + shlex.quote(batch))
        for actor in actors:
            snapshots[actor] = deployment.stations[actor].observe()
            (output / (actor + '-terminal.json')).write_text(json.dumps(snapshots[actor]) + '\n')
        bindings = deployment.bindings
    (output / 'service-terminal.json').write_text(json.dumps(deployment.terminal_service) + '\n')
    outcome = review_outcomes(domain, inputs, truth, snapshots, kind=deployment_name, service=deployment.terminal_service)
    (output / 'independent-outcome.json').write_text(json.dumps(outcome, indent=2) + '\n')
    assert all(value == shared for value in outcome['business_complete'].values()), outcome['business_complete']
    correct = sum(value for batches in outcome['delivered_complete'].values() for value in batches.values())
    assert correct == (9 if shared else 0), correct
    result = {'model_calls': 0, 'operator_authored': True, 'formation_assessed': False,
              'deployment': deployment_name, 'encoding': encoding, 'domain': domain, 'shared': shared,
              'input_sha256': digest(manifest), 'bindings': bindings, 'transfers': transfers,
              'local_source_copies':sum(row['transport']=='local_copy' for row in transfers),
              'private_foreign_visibility_checks':scope_checks,
              'private_source_bytes_transmitted':0 if not shared else None,
              'correct_published_releases': correct,
              'foreign_transfers': sum(row['reader'] != row['owner'] for row in transfers),
              'resources_closed': deployment.closed}
    (output / 'witness.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    matrix = sub.add_parser("matrix")
    matrix.add_argument("--output", type=Path, required=True)
    run = sub.add_parser("smoke")
    run.add_argument("--deployment", choices=DEPLOYMENTS, required=True)
    run.add_argument("--encoding", choices=ENCODINGS, required=True)
    run.add_argument("--domain", choices=DOMAINS, required=True)
    run.add_argument("--scope", choices=("both", "shared", "private"), default="both")
    run.add_argument("--payload-bytes", type=int, default=256)
    run.add_argument("--output", type=Path, required=True)
    full = sub.add_parser('business')
    full.add_argument('--deployment', choices=DEPLOYMENTS, required=True)
    full.add_argument('--encoding', choices=ENCODINGS, required=True)
    full.add_argument('--domain', choices=DOMAINS, required=True)
    full.add_argument('--scope', choices=('both', 'shared', 'private'), default='both')
    full.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.operation == "matrix":
        output = args.output.resolve()
        if output.exists() or output.is_relative_to(ROOT):
            parser.error("Choose a new output file outside the repository")
        result = validate_matrix(output)
    else:
        if args.operation == 'smoke' and not 1 <= args.payload_bytes <= 8192:
            parser.error("--payload-bytes must be between 1 and 8192")
        output = args.output.resolve()
        if output.exists() or output.is_relative_to(ROOT):
            parser.error("Choose a new output path outside the repository")
        scopes = (True, False) if args.scope == "both" else (args.scope == "shared",)
        source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        code = output / 'witness-code'
        code.mkdir(parents=True)
        hashes = {}
        for file in (Path(__file__), Path(__file__).with_name('swarmform_service_witness_codecs.py'),
                     Path(__file__).with_name('swarmform_service_timing_witness.py')):
            data = file.read_bytes()
            (code / file.name).write_bytes(data)
            hashes[file.name] = sha256(data).hexdigest()
        (output / 'source.json').write_text(json.dumps({'source_commit': source,
            'working_tree_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
            'witness_code_sha256': hashes}, indent=2) + '\n')
        result = {"deployment": args.deployment, "encoding": args.encoding,
                  "domain": args.domain, "model_calls": 0,
                  'source_commit': source,
                  "results": [(business(args.deployment, args.encoding, args.domain, shared,
                                        output / ('shared' if shared else 'private')) if args.operation == 'business'
                               else smoke(args.deployment, args.encoding, args.domain, shared,
                                          output / ('shared' if shared else 'private'), args.payload_bytes))
                              for shared in scopes]}
        (output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    if args.operation == 'matrix':
        print(json.dumps({'cells': result['cells'], 'passed': result['passed'], 'model_calls': 0}))
    else:
        print(json.dumps({'deployment': args.deployment, 'encoding': args.encoding,
                          'domain': args.domain, 'validation': args.operation, 'model_calls': 0,
                          'results': [{key: row[key] for key in ('shared', 'correct_published_releases', 'transferred', 'resources_closed') if key in row}
                                      for row in result['results']]}))


if __name__ == "__main__":
    main()
