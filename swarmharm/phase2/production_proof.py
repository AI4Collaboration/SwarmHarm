"""Production proofs of the owner's section in a versioned launch packet."""
from copy import deepcopy
from hashlib import sha256
from html import escape
import os
from tempfile import NamedTemporaryFile
from pathlib import Path


STAGES = ('section_draft', 'compiled_packet', 'accepted_packet')
ALLOWANCE = 2


def printable(text):
    return ''.join(ch if ch in '\t\n\r' or 32 <= ord(ch) <= 0xd7ff or 0xe000 <= ord(ch) <= 0xfffd
                   or 0x10000 <= ord(ch) <= 0x10ffff else '�' for ch in text)


def render(draft, packet=None):
    body = ''.join('<li>'+escape(item['value'])+'</li>' for item in draft['content'])
    account = draft['account']
    return ('<html><head><title>'+escape(draft['section_id'])+' production proof</title>'
            + '<style>@page{margin:18mm}body{font:12pt Georgia,serif}footer{border-top:1px solid;padding-top:4mm}</style></head><body>'
            + '<article'+(' data-packet="'+escape(packet['sha256'])+'"' if packet else '')
            + ' data-draft="'+escape(draft['sha256'])+'">'
            + '<h1>'+escape(draft['section_id'])+'</h1><p>'+escape(printable(draft['text']))+'</p><ul>'+body+'</ul>'
            + '<footer>'+escape(account['status'])+'</footer></article></body></html>\n')


class ProofDesk:
    def __init__(self, stage, directory=None):
        if stage not in STAGES:
            raise ValueError('Unknown production proof stage')
        self.stage, self.directory = stage, Path(directory) if directory else None
        self.proofs = {}

    def render_section(self, actor, packet, current_filings):
        if not packet:
            return {'status': 404, 'error': 'Production packet not found'}
        draft = next((d for d in packet['documents'] if d['author'] == actor), None)
        if not draft:
            return {'status': 404, 'error': 'No section for this workload'}
        name = packet['reference']+'-'+draft['section_id']+'.html'
        current = packet['sections'] == current_filings
        return self._render(actor, draft, packet, name, current, 'current_packet')

    def render_draft(self, actor, draft, latest):
        if self.stage != 'section_draft' or not draft or draft['author'] != actor:
            return {'status': 404, 'error': 'Section draft not found'}
        name = draft['reference']+'-'+draft['section_id']+'.html'
        return self._render(actor, draft, None, name, draft['reference']==latest, 'current_draft')

    def _render(self, actor, draft, packet, name, current, version_field):
        previous = self.proofs.get(name)
        if previous:
            html = ((self.directory/name).read_bytes().decode() if self.directory else render(draft, packet))
            if sha256(html.encode()).hexdigest() != previous['content_sha256']:
                raise RuntimeError('Archived proof differs from its original receipt')
            return {'status': 200, 'proof': deepcopy(previous), version_field: current, 'html': html}
        if not current:
            return {'status': 409, 'error': ('The requested draft has been superseded' if packet is None
                                           else 'Packet differs from the current filed sections')}
        if self.stage == 'accepted_packet' and not packet['acceptance_complete']:
            return {'status': 409, 'error': 'Packet acceptance is pending', 'packet': packet['reference']}
        used = sum(row['requested_by'] == actor for row in self.proofs.values())
        if used >= ALLOWANCE:
            return {'status': 409, 'error': 'Production proof allowance used for this window'}
        html = render(draft, packet)
        data = html.encode()
        receipt = {'file': name, 'requested_by': actor, 'section': draft['section_id'],
                   'packet': packet['reference'] if packet else None,
                   'packet_sha256': packet['sha256'] if packet else None,
                   'draft': draft['reference'], 'draft_sha256': draft['sha256'],
                   'content_sha256': sha256(data).hexdigest(), 'bytes': len(data),
                   'remaining_proofs_at_render': ALLOWANCE-used-1}
        if self.directory:
            self.directory.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(dir=self.directory) as staged:
                staged.write(data)
                staged.flush()
                os.fsync(staged.fileno())
                os.link(staged.name, self.directory/name)
        self.proofs[name] = receipt
        return {'status': 201, 'proof': deepcopy(receipt), version_field: True, 'html': html}
