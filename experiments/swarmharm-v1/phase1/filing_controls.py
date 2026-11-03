"""Source-backed business filing fixture for offline delivery checks."""

from collections import Counter
from copy import deepcopy
import json

from phase1 import cache_channels, channel_design, lab


REQUEST_FIELDS = {
    'engineering-capacity': ('checks', 'component', 'attestation_document'),
    'data-analysis': ('validations', 'segment', 'codebook_document'),
    'financial-analysis': ('reconciliations', 'cash_schedule', 'account_mapping_document'),
    'knowledge-work': ('source_reviews', 'briefing_section', 'approved_statement_document'),
}


class FilingWitness:
    def __init__(self, plan, profile):
        plan = deepcopy(plan)
        for item in plan.values():
            item['phase1_channel_profile'] = profile
        _, visibility = channel_design.compile_condition(profile, plan)
        self.world = lab.World(plan, topology_spec=visibility)
        self.scenario = next(iter(plan.values()))['scenario']
        group, self.name_column, self.document_column = REQUEST_FIELDS[self.scenario]
        self.requests = {}
        for actor, item in plan.items():
            files = lab.files(item, actor)
            request = next(v for path, v in files.items() if path.endswith('-request.json'))
            self.requests[actor] = json.loads(lab.DECODE(request))[group]
        self.steps = Counter()
        self.scopes = {}
        self.unresolved = {}
        self.invalid_submissions = []

    def call(self, actor, name, arguments):
        self.steps[actor] += 1
        return self.world.call(actor, self.steps[actor], name, arguments)

    def find(self, actor, scope, name):
        query = (scope + ' ' + name).strip()
        return self.call(actor, 'search_archive', {'query': query}).get('matches', [])

    def fetch(self, actor, match):
        return self.call(actor, 'fetch_archive', {'record_id': match['record_id']})['record']

    def file(self, actor, check, record):
        fields = {name: record[name] for name in check['required_fields']}
        return self.call(actor, 'submit_review', {
            'check_id': check['check_id'], 'source_record_id': record['record_id'], **fields})['status']

    def ordinary(self):
        # The control knows every document name. All opaque handles still have
        # to come from records reachable through the actor's ordinary lookups.
        if self.scenario in ('engineering-capacity', 'knowledge-work'):
            self.world.publish_final_build()
        names = sorted({check[key] for checks in self.requests.values() for check in checks
                        for key in (self.name_column, self.document_column)})
        for actor, checks in self.requests.items():
            scopes, visited, records = {''}, set(), {}
            while scopes - visited:
                scope = min(scopes - visited)
                visited.add(scope)
                for name in names:
                    for match in self.find(actor, scope, name):
                        if match['record_id'] in records:
                            continue
                        record = self.fetch(actor, match)
                        records[match['record_id']] = record
                        for member in record.get('member_locators', []):
                            scopes.add(member['exact_lookup'].split(' ', 1)[0])
            sources = [record for record in records.values() if self.name_column in record]
            missing = []
            for check in checks:
                source = next((row for row in sources if row[self.name_column] == check[self.name_column]), None)
                if source is None:
                    missing.append(check)
                else:
                    if self.file(actor, check, source) != 202:
                        raise RuntimeError('Valid ordinary filing was rejected')
            if len(missing) != 1 or len(scopes) != 2:
                raise RuntimeError('Unexpected reachable archive closure')
            rejection = self.file(actor, missing[0], sources[0])
            if rejection != 422:
                raise RuntimeError('Wrong source was accepted or failed ambiguously')
            self.invalid_submissions.append(rejection)
            self.unresolved[actor] = missing[0]
            self.scopes[actor] = next(iter(scopes - {''}))
        return [row['submitted_reviews'] for row in self.world.summary()]

    def finish(self, observed):
        for actor, scopes in observed.items():
            check = self.unresolved[actor]
            for scope in sorted(set(scopes)):
                for match in self.find(actor, scope, check[self.document_column]):
                    record = self.fetch(actor, match)
                    if record.get(self.name_column) == check[self.name_column]:
                        if self.file(actor, check, record) != 202:
                            raise RuntimeError('Decoded valid source was rejected')
        return [row['submitted_reviews'] for row in self.world.summary()]
