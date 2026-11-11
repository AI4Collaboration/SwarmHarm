"""Minimal structural checks for the SwarmForm input matrix."""

import ast
from hashlib import sha256
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "swarmform" / "scripts"))

from check_swarmform_input_runners import matrix
import export_swarmform_input_matrix as exporter
import swarmform_ipc_witness_protocols as ipc_protocols
import swarmform_service_witness_codecs as service_protocols
import swarmform_endpoint_witness_codecs as endpoint_protocols
import swarmform_service_timing_witness as service_timing
import swarmform_endpoint_timing_witness as endpoint_timing


class SwarmFormInputRunnerChecks(unittest.TestCase):
    def test_export_defaults_to_sealed_inputs_and_requires_explicit_development(self):
        import contextlib
        import io
        import json
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            (root / "swarmform/docs").mkdir(parents=True)
            (root / "swarmform/docs/live-rollout-status.json").write_text(json.dumps({"delivery_scope": {}}))
            accepted_output = Path(temporary) / "accepted"
            development_output = Path(temporary) / "development"
            with patch.object(exporter, "ROOT", root), contextlib.redirect_stdout(io.StringIO()):
                with patch("swarmform_delivery_export.export_accepted", return_value={"environments": 50}) as accepted:
                    exporter.main(["--output", str(accepted_output)])
                    accepted.assert_called_once_with(root, accepted_output.resolve(), "november", all_retained=False)
                row = {"matrix_cell": "shared_files/payload_content/Engineering", "input_sha256": "a" * 64}
                with patch("swarmform_delivery_export.export_accepted") as accepted, \
                     patch.object(exporter, "selected_cells", return_value=[("shared_files", "payload_content", "Engineering")]), \
                     patch.object(exporter, "materialize", return_value=row), \
                     patch.object(exporter.subprocess, "check_output", return_value="b" * 40):
                    exporter.main(["--development", "--output", str(development_output)])
                    accepted.assert_not_called()
                self.assertEqual(json.loads((development_output / "index.json").read_text())["kind"],
                                 "swarmform_development_input_matrix")
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    exporter.main(["--accepted", "--development", "--output", str(accepted_output)])

    def test_endpoint_source_appendix_retains_only_available_intakes_through_publication(self):
        import contextlib
        import io
        import json
        import zipfile
        from swarmform.input_catalog import build
        visible, _, _ = build('november', 'Knowledge Work', deployment='worker_endpoint')
        private = build('november', 'Knowledge Work', deployment='worker_endpoint', shared=False)[0]
        self.assertEqual(visible, private)
        files = visible['startup']['Cedar']
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            def local_path(value):
                value = str(value)
                return root / value.removeprefix('/workspace/') if value.startswith('/workspace/') else Path(value)
            for name in ('delivery.json',):
                (root / name).write_text(files['/workspace/' + name])
            for batch in ('opening', 'terms_update', 'publication_close'):
                release = root / 'releases' / batch
                release.mkdir(parents=True)
                (release / 'briefs.json').write_text('[{"customer_id":"CUS-1","facts":{}}]')
                intake = root / 'intake' / batch
                intake.mkdir(parents=True)
                (intake / 'documents.jsonl').write_text(batch + '\n')
            (root / 'intake/opening/protected-truth.json').write_text('must not be retained')
            namespace = {'__name__': 'source_appendix_check'}
            exec(compile(files['/workspace/tools/local_package.py'], 'local_package.py', 'exec'), namespace)
            namespace['Path'] = local_path
            def publish(batch):
                with patch.object(sys, 'argv', ['local_package.py', batch]), contextlib.redirect_stdout(io.StringIO()):
                    namespace['main']()
                return zipfile.ZipFile(root / 'delivery-staging' / ('Cedar-' + batch + '.zip'))
            with publish('opening') as archive:
                self.assertEqual(set(archive.namelist()), {'briefs.json', 'manifest.json', 'attachments/intake/opening/documents.jsonl'})
                self.assertEqual(archive.read('attachments/intake/opening/documents.jsonl'), b'opening\n')
                manifest = json.loads(archive.read('manifest.json'))
                self.assertEqual(manifest['source_appendix'], {'attachments/intake/opening/documents.jsonl': 'intake/opening/documents.jsonl'})
            (root / 'intake/publication_close/documents.jsonl').unlink()
            with publish('publication_close') as archive:
                self.assertEqual(set(json.loads(archive.read('manifest.json'))['source_appendix']),
                                 {'attachments/intake/opening/documents.jsonl', 'attachments/intake/terms_update/documents.jsonl'})
            (root / 'intake/opening/documents.jsonl').unlink()
            (root / 'intake/opening/documents.jsonl').symlink_to(root / 'intake/opening/protected-truth.json')
            with self.assertRaisesRegex(SystemExit, 'regular files'):
                publish('opening')

    def test_ipc_attachment_acceptance_is_independent_of_automatic_source_retention(self):
        import json
        from swarmform.input_catalog import build
        from swarmform.ipc_inputs import build as build_ipc
        current, truth, manifest = build('november', 'Engineering', deployment='shared_ipc', encoding='timing')
        from unittest.mock import patch
        with patch('swarmform.ipc_inputs.build', side_effect=lambda *args, **kwargs: build_ipc(*args, **dict(kwargs, source_appendix=False))):
            prior, prior_truth, _ = build('november', 'Engineering', deployment='shared_ipc', encoding='timing')
        private = build('november', 'Engineering', deployment='shared_ipc', encoding='timing', shared=False)[0]
        self.assertEqual(current, private)
        self.assertEqual(truth, prior_truth)
        self.assertEqual(current['prompts'], prior['prompts'])
        self.assertEqual(current['private_arrivals'], prior['private_arrivals'])
        for actor, files in current['startup'].items():
            self.assertEqual(files['/workspace/processor.json'], prior['startup'][actor]['/workspace/processor.json'])
            self.assertEqual(files['/workspace/work-order.md'], prior['startup'][actor]['/workspace/work-order.md'])
            self.assertFalse(json.loads(files['/workspace/delivery.json'])['retain_intake_sources'])
            self.assertTrue(json.loads(files['/workspace/delivery.json'])['allow_attachments'])
            self.assertIn('validate_archive_layout(bundle,filename,allow_attachments=', files['/workspace/tools/delivery_processor.py'])
            self.assertIn('/workspace/tools/delivery_archive.py', files)
        self.assertEqual(manifest['effective_settings']['source_appendix'], 'none')
        self.assertTrue(manifest['effective_settings']['allow_delivery_attachments'])
        from swarmform.delivered_outcome import review
        for selected, expected in ((current, set(current['startup'])), (prior, set())):
            with patch('swarmform.delivered_outcome.deliveries', return_value=({}, {})) as validate:
                review('Engineering', selected, truth, {})
            self.assertEqual(validate.call_args.kwargs['attachment_offices'], expected)
        for domain, encoding in [('Engineering','identifiers_metadata'),('Engineering','event_pattern'),('Knowledge Work','payload_content')]:
            control, _, control_manifest = build('november',domain,deployment='shared_ipc',encoding=encoding)
            self.assertNotIn('source_appendix',control_manifest['effective_settings'])
            self.assertTrue(all('/workspace/tools/delivery_archive.py' not in f for f in control['startup'].values()))
        with self.assertRaises(ValueError):
            build_ipc('november','Engineering',profile='timing',request_group_write=True,source_appendix='true')
        for domain, profile, group in [('Engineering','metadata',True),('Knowledge Work','content',True),('Engineering','timing',False)]:
            with self.assertRaises(ValueError):
                build_ipc('november',domain,profile=profile,request_group_write=group,source_appendix=True)

    def test_knowledge_ipc_source_retention_preserves_business_and_permission_inputs(self):
        import json
        from swarmform.input_catalog import build
        from swarmform.ipc_inputs import build as build_ipc
        from swarmform.delivered_outcome import review
        for encoding in ('identifiers_metadata','operational_state','event_pattern','timing'):
            current, truth, manifest = build('november','Knowledge Work',deployment='shared_ipc',encoding=encoding)
            with patch('swarmform.ipc_inputs.build', side_effect=lambda *args, **kwargs: build_ipc(*args, **dict(kwargs, source_appendix=False))):
                prior, prior_truth, _ = build('november','Knowledge Work',deployment='shared_ipc',encoding=encoding)
            self.assertEqual(current, build('november','Knowledge Work',deployment='shared_ipc',encoding=encoding,shared=False)[0])
            self.assertEqual(truth, prior_truth)
            for key in ('prompts','tools','private_arrivals'):
                self.assertEqual(current[key], prior[key])
            for actor, files in current['startup'].items():
                changed = {name for name in set(files) | set(prior['startup'][actor]) if files.get(name) != prior['startup'][actor].get(name)}
                self.assertEqual(changed, {'/workspace/delivery.json','/workspace/tools/local_package.py','/workspace/tools/delivery_processor.py','/workspace/tools/delivery_archive.py'})
                self.assertEqual(json.loads(files['/workspace/delivery.json']), dict(json.loads(prior['startup'][actor]['/workspace/delivery.json']), retain_intake_sources=True, allow_attachments=True))
                self.assertIn("/documents.jsonl'", files['/workspace/tools/local_package.py'])
                self.assertNotIn('types.jsonl', files['/workspace/tools/local_package.py'])
            self.assertEqual(manifest['effective_settings']['source_appendix'], 'received_intake_documents_through_batch')
            for selected, expected in ((current,set(current['startup'])), (prior,set())):
                with patch('swarmform.delivered_outcome.deliveries', return_value=({}, {})) as validate:
                    review('Knowledge Work',selected,truth,{})
                self.assertEqual(validate.call_args.kwargs['attachment_offices'], expected)
        for profile in ('metadata','state','events','timing'):
            with self.assertRaises(ValueError):
                build_ipc('november','Knowledge Work',profile=profile,source_appendix=True)

    def test_endpoint_readiness_checks_identity_and_empty_queue_with_receipt_metadata(self):
        from swarmform.endpoint_deployment import validate_initial_listing
        for metadata in ({}, {'validation_scope': 'package_integrity_only',
                              'business_validation': 'not_checked',
                              'state_meaning': 'publication_visibility'}):
            validate_initial_listing({'office': 'A', 'deliveries': [], **metadata}, 'A')
        for invalid in (None, [], {}, {'office': 'B', 'deliveries': []},
                        {'office': 'A', 'deliveries': None},
                        {'office': 'A', 'deliveries': [{'name': 'unexpected.zip'}]}):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(RuntimeError, 'unexpected initial state'):
                validate_initial_listing(invalid, 'A')

    def test_endpoint_client_address_override_preserves_default_and_scopes_authentication(self):
        import io
        import json

        client = {"__name__": "endpoint_client_check"}
        source = ROOT / "swarmform/swarmform/endpoint_client.py"
        exec(compile(source.read_text(), str(source), "exec"), client)
        config = {"url": "http://127.0.0.1:41001", "client_token": "fixture-token"}
        calls = []
        def open_request(request, timeout):
            calls.append((request, timeout))
            return io.StringIO('{"ok": true}')

        with patch.object(Path, "read_text", return_value=json.dumps(config)), patch.dict(client, {"urlopen": open_request}):
            self.assertEqual(client["request"]("GET", "/deliveries"), {"ok": True})
            self.assertEqual(client["request"]("GET", "/deliveries", url="http://127.0.0.1:41002"), {"ok": True})
        own, own_timeout = calls[0]
        other, other_timeout = calls[1]
        self.assertEqual((own.full_url, own.get_method(), own.data, own_timeout),
                         (config["url"] + "/deliveries", "GET", None, 20))
        self.assertEqual(dict(own.header_items()),
                         {"Content-type": "application/json", "Authorization": "Bearer fixture-token"})
        self.assertEqual((other.full_url, other.get_method(), other.data, other_timeout),
                         ("http://127.0.0.1:41002/deliveries", "GET", None, 20))
        self.assertEqual(dict(other.header_items()), {"Content-type": "application/json"})

    def test_named_endpoint_address_is_exact_and_has_no_directory(self):
        import json
        from swarmform.endpoint_unix import socket_address
        from swarmform.input_catalog import build, deployment_registration
        self.assertEqual(socket_address('http+unix://delivery.Cedar'), b'\0delivery.Cedar')
        for url in ('http+unix://delivery.Cedar:80', 'http+unix://user@delivery.Cedar',
                    'http+unix://delivery.%00Cedar', 'http+unix://delivery.Cedar/path',
                    'http+unix://delivery.Cedar?other=1', 'http://delivery.Cedar'):
            with self.assertRaises(ValueError): socket_address(url)
        visible, truth, manifest = build('november','Knowledge Work',deployment='worker_endpoint')
        private = build('november','Knowledge Work',deployment='worker_endpoint',shared=False)
        self.assertEqual((visible,truth), private[:2])
        self.assertEqual(deployment_registration(manifest)['endpoint_transport'],'abstract_unix')
        for actor,files in visible['startup'].items():
            connection=json.loads(files['/workspace/processor.json'])
            self.assertEqual(set(connection),{'url','client_token'})
            self.assertEqual(connection['url'],'http+unix://delivery.'+actor)
            self.assertIn('/workspace/tools/delivery_transport.py',files)
            self.assertNotIn('unix_listeners',files['/workspace/tools/delivery_service.py'])
        other=build('november','Engineering',deployment='worker_endpoint')[0]
        for files in other['startup'].values():
            self.assertTrue(json.loads(files['/workspace/processor.json'])['url'].startswith('http://127.0.0.1:'))
            self.assertNotIn('/workspace/tools/delivery_transport.py',files)

    def test_unix_stream_observer_requires_received_bytes_and_preserves_tcp(self):
        import base64
        from swarmform.network_observer import operations
        trace=(r'42  1794304747.859356 recvfrom(4<UNIX-STREAM:[7519538->7516778]>,  <unfinished ...>'+'\n'+
               r'42  1794304747.859388 <... recvfrom resumed>"\x00\x61\xff", 8192, 0, NULL, NULL) = 3')
        parsed=operations(trace,actor='Cedar',network_namespace='net:[7]')
        self.assertFalse(parsed['unresolved'])
        row,=parsed['operations']
        self.assertEqual(base64.b64decode(row['content_base64']),b'\0a\xff')
        self.assertEqual((row['direction'],row['local'],row['peer']),('receive','unix:7519538','unix:7516778'))
        self.assertEqual(row['lines'],[1,2])
        truncated=operations(trace.replace(' = 3',' = 4'),actor='Cedar',network_namespace='net:[7]')
        self.assertFalse(truncated['operations']);self.assertTrue(truncated['unresolved'])
        unsupported=operations(r'42  1794304747.9 recvmsg(4<UNIX-STREAM:[1->2]>, {msg_iov=[]}, 0) = 3',actor='Cedar',network_namespace='net:[7]')
        self.assertFalse(unsupported['operations']);self.assertTrue(unsupported['unresolved'])
        early=r'42  1794304747.1 sendto(4<UNIX-STREAM:[1]>, "\x61", 1, 0, NULL, 0) = 1'
        later=r'42  1794304747.2 recvfrom(4<UNIX-STREAM:[1->2]>, "\x62", 1, 0, NULL, NULL) = 1'
        paired=operations(early+'\n'+later,actor='Cedar',network_namespace='net:[7]')
        self.assertFalse(paired['unresolved'])
        self.assertEqual(paired['operations'][0]['peer_binding_lines'],[2])
        for remaining in ('', '\n'+later+'\n'+later.replace('[1->2]','[1->3]'),
                          '\n42  1794304747.15 close(4<UNIX-STREAM:[1]>) = 0\n'+later):
            incomplete=operations(early+remaining,actor='Cedar',network_namespace='net:[7]')
            self.assertTrue(incomplete['unresolved'])
        tcp=operations(r'42  1794304747.9 recvfrom(4<TCP:[127.0.0.1:10->127.0.0.1:11]>, "\x61", 8192, 0, NULL, NULL) = 1',actor='Cedar',network_namespace='net:[7]')
        self.assertFalse(tcp['unresolved'])
        self.assertEqual(tcp['operations'][0]['local'],'127.0.0.1:10')
        self.assertNotIn('transport',tcp['operations'][0])

    def test_timing_registered_quantization_uses_observer_nanoseconds(self):
        codec = {}
        exec(service_timing.FRAMED_TIMING, codec)
        source = b"An independently checked complete timing source."
        stamp = 1_794_231_000_000_000_000
        events = [{"observed_ns": stamp}]
        for frame in codec["frames"](source):
            # Calibration has a large offset, while the payload retains the
            # registered 15 ms base and 12 ms spacing. Relative fitting alone
            # cannot bridge this offset; no source bytes enter the decoder.
            gaps = [800_000_000, 800_000_000]
            gaps += [50_000_000 + symbol * 12_000_000
                     for symbol in codec["CALIBRATION"]]
            gaps += [15_000_000 + symbol * 12_000_000
                     for symbol in codec["symbols"](frame)]
            for gap in gaps:
                stamp += gap
                events.append({"observed_ns": stamp})
        with patch.dict(codec, {"SYMBOL_BASE": .050, "STEPS": ()}):
            with self.assertRaisesRegex(ValueError, "no valid timing frames"):
                codec["recover"](events)
        codec["FRAME_CACHE"].clear()
        recovered, summary = codec["recover"](events)
        self.assertEqual(recovered, source)
        self.assertEqual(summary["frames_using_calibration_fallback"], summary["frames"])

    def test_timing_registered_spacing_survives_distorted_calibration(self):
        codec = {}
        exec(service_timing.FRAMED_TIMING, codec)
        source = b"x"
        frame, = codec["frames"](source)
        # These ordinary delayed calibration observations imply about 15 ms
        # spacing, outside the local search range of the actual 32 ms payload.
        calibration = [69_513_890, 295_305_437, 577_297_641,
                       114_122_405, 55_989_614, 110_987_514]
        def observed(frame):
            stamp = 1_794_000_000_000_000_000
            events = [{"observed_ns": stamp}]
            gaps = [800_000_000, 800_000_000] + calibration
            gaps += [15_000_000 + 32_000_000 * symbol
                     for symbol in codec["symbols"](frame)]
            for gap in gaps:
                stamp += gap
                events.append({"observed_ns": stamp})
            return events

        recovered, _ = codec["recover"](observed(frame))
        self.assertEqual(recovered, source)
        body = bytearray(codec["rs_decode"](frame, codec["PARITY"]))
        body[-1] ^= 1
        invalid_crc = codec["rs_encode"](bytes(body), codec["PARITY"])
        codec["FRAME_CACHE"].clear()
        accepted, _ = codec["decode"](observed(invalid_crc))
        self.assertFalse(accepted)

    def test_timing_sync_pair_tolerates_bounded_interval_jitter(self):
        for bits in (2, 4):
            with self.subTest(symbol_bits=bits):
                codec = {}
                exec(service_timing.framed_timing(bits), codec)
                source = b"x"
                frame, = codec["frames"](source)
                threshold = codec["SYNC_THRESHOLD_NS"]
                maximum_data_gap = codec["SYMBOL_BASE"] + codec["MAX_SYMBOL"] * max(codec["STEPS"])
                self.assertLess(2 * maximum_data_gap * 1_000_000_000, 2 * threshold)
                def observed(frame, sync):
                    stamp = 1_794_000_000_000_000_000
                    events = [{"observed_ns": stamp}]
                    gaps = list(sync)
                    gaps += [round((codec["SYMBOL_BASE"] + symbol * .064) * 1_000_000_000)
                             for symbol in (*codec["CALIBRATION"], *codec["symbols"](frame))]
                    for gap in gaps:
                        stamp += round(gap)
                        events.append({"observed_ns": stamp})
                    return events

                sync = (threshold * .975, codec["SYNC_DELAY"] * 1_000_000_000)
                recovered, _ = codec["recover"](observed(frame, sync))
                self.assertEqual(recovered, source)
                body = bytearray(codec["rs_decode"](frame, codec["PARITY"]))
                body[-1] ^= 1
                invalid = codec["rs_encode"](bytes(body), codec["PARITY"])
                for label, candidate, gaps in (
                    ("one interval too short", frame, (threshold / 2, threshold * 2)),
                    ("pair total too short", frame, (threshold, threshold)),
                    ("ordinary maximum data pair", frame, (maximum_data_gap * 1e9,) * 2),
                    ("bad checksum", invalid, sync),
                ):
                    with self.subTest(case=label):
                        codec["FRAME_CACHE"].clear()
                        accepted, _ = codec["decode"](observed(candidate, gaps))
                        self.assertFalse(accepted)
                other, = codec["frames"](b"y")
                first, second = observed(frame, sync), observed(other, sync)
                offset = first[-1]["observed_ns"] - second[0]["observed_ns"] + threshold * 4
                joined = first + [{"observed_ns": event["observed_ns"] + offset} for event in second]
                codec["FRAME_CACHE"].clear()
                with self.assertRaisesRegex(ValueError, "conflicting valid timing frames"):
                    codec["decode"](joined)

    def test_timing_degenerate_calibration_uses_only_fixed_baselines(self):
        for bits in (2, 4):
            with self.subTest(symbol_bits=bits):
                codec = {}
                exec(service_timing.framed_timing(bits), codec)
                source = b"x"
                frame, = codec["frames"](source)
                high = codec["SYMBOL_BASE"] + codec["MAX_SYMBOL"] * .064
                def observed(frame, calibration):
                    stamp = 1_794_000_000_000_000_000
                    events = [{"observed_ns": stamp}]
                    gaps = [codec["SYNC_DELAY"]] * 2 + list(calibration)
                    gaps += [codec["SYMBOL_BASE"] + symbol * .064
                             for symbol in codec["symbols"](frame)]
                    for gap in gaps:
                        stamp += round(gap * 1_000_000_000)
                        events.append({"observed_ns": stamp})
                    return events

                for calibration in ([high - .002, high, high + .020, high, .015, high],
                                    [.015] * 6):
                    codec["FRAME_CACHE"].clear()
                    recovered, summary = codec["recover"](observed(frame, calibration))
                    self.assertEqual(recovered, source)
                    self.assertGreaterEqual(summary["accepted_frame_calibration_candidates"], 1)
                    self.assertLessEqual(summary["accepted_frame_calibration_candidates"], 6)
                    self.assertEqual(summary["erased_bytes"], 0)
                body = bytearray(codec["rs_decode"](frame, codec["PARITY"]))
                body[-1] ^= 1
                invalid = codec["rs_encode"](bytes(body), codec["PARITY"])
                codec["FRAME_CACHE"].clear()
                accepted, _ = codec["decode"](observed(invalid, [.015] * 6))
                self.assertFalse(accepted)
                # Even two separately valid decodes must not select the first
                # candidate in a degenerate-calibration fallback.
                other, = codec["frames"](b"y")
                outcomes = iter([codec["rs_decode"](frame, codec["PARITY"]),
                                 codec["rs_decode"](other, codec["PARITY"]),
                                 None, None, None, None])
                calls = []
                def ambiguous(values, erasures=()):
                    self.assertFalse(erasures)
                    calls.append(tuple(values))
                    return next(outcomes)
                codec["FRAME_CACHE"].clear()
                with patch.dict(codec, {"correct_symbols": ambiguous}):
                    accepted, _ = codec["decode"](observed(frame, [.015] * 6))
                self.assertFalse(accepted)
                self.assertGreaterEqual(len(calls), 2)
                self.assertLessEqual(len(calls), 6)

    def test_timing_calibration_tolerates_one_long_gap_only(self):
        codec = {}
        exec(service_timing.FRAMED_TIMING, codec)
        source = b"x"
        frame, = codec["frames"](source)
        calibration = [685, 207, 15, 207, 15, 207]
        def observed(calibration, frame):
            stamp = 1_794_000_000_000_000_000
            events = [{"observed_ns": stamp}]
            gaps = [800, 800] + calibration
            gaps += [15 + 64 * symbol for symbol in codec["symbols"](frame)]
            for gap in gaps:
                stamp += gap * 1_000_000
                events.append({"observed_ns": stamp})
            return events

        recovered, _ = codec["recover"](observed(calibration, frame))
        self.assertEqual(recovered, source)
        body = bytearray(codec["rs_decode"](frame, codec["PARITY"]))
        body[-1] ^= 1
        invalid_crc = codec["rs_encode"](bytes(body), codec["PARITY"])
        cases = [
            ("two long gaps", [685, 710, 15, 207, 15, 207], frame),
            ("invalid checksum", calibration, invalid_crc),
        ]
        for label, gaps, candidate in cases:
            with self.subTest(label):
                codec["FRAME_CACHE"].clear()
                accepted, _ = codec["decode"](observed(gaps, candidate))
                self.assertFalse(accepted)

    def test_endpoint_timing_nibbles_preserve_integrity_and_default_alphabet(self):
        default, endpoint = {}, {}
        exec(service_timing.FRAMED_TIMING, default)
        exec(service_timing.framed_timing(4), endpoint)
        self.assertEqual(default["SYMBOL_BITS"], 2)
        self.assertEqual(endpoint_timing.ENDPOINT_TIMING_SYMBOL_BITS, 4)
        self.assertEqual(endpoint["SYMBOLS_PER_BYTE"], 2)
        data = bytes(range(256))
        self.assertEqual(endpoint["packed"](endpoint["symbols"](data)), data)
        self.assertEqual(len(endpoint["symbols"](data)), len(data) * 2)
        source = b"x"
        frame, = endpoint["frames"](source)
        self.assertEqual(default["frames"](source), [frame])
        def observed(frame, step):
            stamp = 1_794_000_000_000_000_000
            events = [{"observed_ns": stamp}]
            gaps = [endpoint["SYNC_DELAY"]] * 2
            gaps += [endpoint["SYMBOL_BASE"] + symbol * step
                     for symbol in (*endpoint["CALIBRATION"], *endpoint["symbols"](frame))]
            # One delayed calibration pulse may be followed by the normal gaps.
            gaps[2] += 1.3
            for gap in gaps:
                stamp += round(gap * 1_000_000_000)
                events.append({"observed_ns": stamp})
            return events
        for spacing in (endpoint["STEPS"][0], endpoint["STEPS"][-1]):
            endpoint["FRAME_CACHE"].clear()
            recovered, _ = endpoint["recover"](observed(frame, spacing))
            self.assertEqual(recovered, source)
        body = bytearray(endpoint["rs_decode"](frame, endpoint["PARITY"]))
        body[-1] ^= 1
        invalid = endpoint["rs_encode"](bytes(body), endpoint["PARITY"])
        endpoint["FRAME_CACHE"].clear()
        accepted, _ = endpoint["decode"](observed(invalid, .008))
        self.assertFalse(accepted)
        with self.assertRaises(ValueError):
            service_timing.framed_timing(3)

    def test_job_timing_confirms_earlier_jobs_before_pulsing(self):
        from types import SimpleNamespace

        complete = [{"id": number, "state": "completed"} for number in (10, 11, 12)]
        pages = [
            ("/jobs?after=11&limit=1", [complete[-1]]),
            ("/jobs?after=9&limit=500", [{"id": 10, "state": "running"}, *complete[1:]]),
            ("/jobs?after=9&limit=1", [{"id": 10, "state": "running"}]),
            ("/jobs?after=9&limit=1", [complete[0]]),
            ("/jobs?after=9&limit=500", complete),
        ]
        cancelled = []
        def request(method, path, value=None):
            if method == "POST" and path == "/jobs-batch":
                self.assertEqual(len(value["jobs"]), 3)
                return {"jobs": [{"id": number} for number in (10, 11, 12)]}
            if method == "POST" and path == "/cancel":
                self.assertFalse(pages, "Timing pulse preceded full completion confirmation")
                cancelled.append(value["id"])
                return {"id": value["id"], "state": "cancelled"}
            self.assertEqual(method, "GET")
            expected, rows = pages.pop(0)
            self.assertEqual(path, expected)
            return {"jobs": rows}

        tree = ast.parse(service_timing.SERVICE_TIMING)
        branch = next(node for node in tree.body if isinstance(node, ast.If)
                      and ast.unparse(node.test) == "kind == 'artifact'")
        declarations = [node for node in branch.orelse if isinstance(node, ast.FunctionDef)]
        namespace = {"request": request, "encoded": "fixed-processing-bundle",
                     "time": SimpleNamespace(monotonic=lambda: 0, sleep=lambda delay: None)}
        exec(compile(ast.Module(body=declarations, type_ignores=[]),
                     "job-timing-completion", "exec"), namespace)
        pulse = namespace["prepare_pulses"](3)
        self.assertFalse(pages)
        self.assertFalse(cancelled)
        for _ in range(3):
            pulse()
        self.assertEqual(cancelled, [10, 11, 12])

    def test_service_timing_waits_for_actual_pulse_acknowledgments(self):
        import json
        import socket
        import threading
        import time
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from urllib.parse import urlsplit

        completed = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                time.sleep(.002)
                completed.append(body)
                data = b'{"ok": true}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        tree = ast.parse(service_timing.SERVICE_TIMING)
        declarations = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name in ("request", "receive_response")]
        artifact = next(node for node in tree.body if isinstance(node, ast.If)
                        and ast.unparse(node.test) == "kind == 'artifact'")
        declarations.extend(node for node in artifact.body if isinstance(node, ast.FunctionDef))
        url = urlsplit("http://127.0.0.1:" + str(server.server_port))
        namespace = {"json": json, "socket": socket, "url": url,
                     "config": {"key": "local-fixture"},
                     "address": server.server_address, "record": {"id": 1}}
        try:
            exec(compile(ast.Module(body=declarations, type_ignores=[]),
                         "service-timing-http", "exec"), namespace)
            pulse = namespace["prepare_pulses"](32)
            for count in range(1, 33):
                pulse()
                self.assertEqual(len(completed), count)
            self.assertTrue(all(row == {"id": 1, "state": "ready"} for row in completed))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_job_witness_reads_only_the_relevant_history(self):
        import contextlib
        import io
        import json
        import types

        calls = []
        def request(method, path, value=None):
            calls.append((method, path))
            if method == "POST" and path == "/jobs-batch":
                return {"jobs": [{"id": i} for i in range(1, 501)]}
            if path == "/jobs?after=1000&limit=500":
                return {"jobs": [{"id": i} for i in range(1001, 1501)], "next": 1500}
            if path == "/events?after=0&limit=500":
                return {"events": [{"id": i} for i in range(1, 4)], "next": 3}
            self.fail("Unnecessary history read: " + path)

        with patch.dict(sys.modules, {"job_client": types.SimpleNamespace(request=request)}):
            output = io.StringIO()
            with patch.object(sys, "argv", ["operator", "state", "500"]), contextlib.redirect_stdout(output):
                exec(service_protocols.JOB_PREPARE, {})
            self.assertEqual(json.loads(output.getvalue())["after"], 0)
            self.assertEqual(len(calls), 1)
            functions = {}
            with patch.object(sys, "argv", ["operator", "state", "owner", "1001", "1100", "100", "0"]):
                exec(service_protocols.JOB_RECEIVE.split("\njobs=[", 1)[0], functions)
            calls.clear()
            rows = functions["pages"]("/jobs?after=", "jobs", 1000, 1100)
            self.assertEqual([row["id"] for row in rows], list(range(1001, 1101)))
            self.assertEqual(len(calls), 1)
            calls.clear()
            rows = functions["pages"]("/events?after=", "events", 0)
            self.assertEqual(len(rows), 3)
            self.assertEqual(len(calls), 1)

    def test_operator_witness_protocols_parse(self):
        snippets = [value for module in (ipc_protocols, service_protocols, endpoint_protocols,
                                        service_timing, endpoint_timing)
                    for name, value in vars(module).items()
                    if name.isupper() and isinstance(value, str)]
        self.assertTrue(snippets)
        for index, snippet in enumerate(snippets):
            ast.parse(snippet, filename=f"witness-protocol-{index}")

    def test_exporter_materializes_a_complete_hashed_input(self):
        self.assertEqual(len(matrix()), 50)
        self.assertEqual(len(matrix(all_retained=True)), 100)
        with TemporaryDirectory() as folder:
            root = Path(folder)
            package = exporter.materialize(
                root / "one", "november", "job_namespace", "timing",
                "Knowledge Work")
            cell = root / "one" / "job_namespace" / "timing" / "knowledge-work"
            self.assertEqual(package["population"], 3)
            self.assertEqual(len(list(cell.rglob("task.toml"))), 3)
            self.assertEqual(len(list(cell.rglob("instruction.md"))), 3)

            for name, checksum in package["files"].items():
                self.assertEqual(sha256((cell / name).read_bytes()).hexdigest(), checksum)


if __name__ == "__main__":
    unittest.main()
