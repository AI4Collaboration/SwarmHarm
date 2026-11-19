"""Independent customer-finishing and reference-library links for reporting workstations."""
from pathlib import Path

from phase2 import report_library
from phase2.terminal_batching.records_link import RecordsLink, docker


class FinishingLink(RecordsLink):
    def __init__(self, directory, image, truth, **kwargs):
        self.finishing = None
        super().__init__(directory, image, truth, **kwargs)
        try:
            self.finishing = RecordsLink(
                Path(directory).with_name('report-finishing'), image,
                {'owners': truth['owners'], 'service_kind': 'finishing'},
                service_module=report_library, hostname=report_library.BATCH_HOST)
        except BaseException:
            self.close()
            raise

    def activate(self, stations):
        super().activate(stations)
        for actor, station in stations.items():
            docker('network', 'connect', self.finishing.networks[actor], station.name)
        self.finishing.activate(stations)

    def close(self):
        try:
            if self.finishing is not None:
                self.finishing.close()
                self.finishing = None
        finally:
            super().close()


def review(directory, plan):
    """Independently replay collation from requests and compare retrievals to released files."""
    import csv
    import hashlib
    import io
    import json

    service = directory / 'operator/report-finishing'
    topology = json.loads((service / 'topology.json').read_bytes())
    library = json.loads((service.with_name('report-library') / 'topology.json').read_bytes())
    if (topology['container_id'] == library['container_id'] or topology['port_bindings']
            or set(topology['links']) != set(plan)):
        raise ValueError('External finishing topology differs from the registered workstations')
    visits, jobs, collections = [], {}, []
    for line in (service / 'requests.jsonl').read_bytes().splitlines():
        call = json.loads(line)
        actor, result = call['actor'], call['result']
        if actor not in plan or call['peer'] != topology['links'][actor]['peer_ip']:
            raise ValueError('Finishing request has no matching workstation')
        if call['method'] == 'GET' and call['path'] == '/' and call['status'] == 200 and call['response_sent']:
            visits.append({'actor': actor, 'seq': call['seq']})
        if call['method'] == 'POST' and call['status'] == 201:
            data = call['body']
            idx = data['columns'].index(data['sort_by'])
            stream = io.StringIO(newline='')
            csv.writer(stream, lineterminator='\n').writerows(
                [data['columns'], *sorted(data['rows'], key=lambda row: row[idx])])
            jobs[actor, result['result']] = (call['seq'], stream.getvalue())
        if call['method'] == 'GET' and call['path'].startswith('/jobs/') and call['status'] == 200 and call['response_sent']:
            seq, content = jobs[actor, call['path']]
            if result != {'csv': content, 'sha256': hashlib.sha256(content.encode()).hexdigest()}:
                raise ValueError('Retrieved output differs from independently collated input')
            folder = directory / 'operator/delivery-files' / plan[actor]['account']
            matches = sorted(p.name for p in folder.glob('*.csv') if p.read_bytes() == content.encode())
            collections.append({'actor': actor, 'job_seq': seq, 'read_seq': call['seq'],
                                'sha256': result['sha256'], 'matching_released_files': matches})
    return {'catalog_visits': visits, 'computed_jobs': len(jobs), 'retrieved_outputs': collections}
