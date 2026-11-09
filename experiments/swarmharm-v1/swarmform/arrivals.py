"""Private source delivery and notice accounting for a persistent workday."""

from hashlib import sha256
from pathlib import PurePosixPath
import time


def file_hashes(files):
    return {path: sha256(content.encode()).hexdigest() for path, content in sorted(files.items())}


class IntakeSchedule:
    """Only new private source versions can produce a pending business notice."""

    def __init__(self, private, offsets, *, activated_at):
        if not offsets or next(iter(offsets.values())) != 0 or list(offsets.values()) != sorted(set(offsets.values())):
            raise ValueError('Arrival offsets must start at zero and increase strictly')
        if any(set(batches) != set(offsets) for batches in private.values()):
            raise ValueError('Each station needs every registered batch')
        self.private, self.offsets = private, dict(offsets)
        self.activated_at = activated_at
        self.receipts = {}
        self.notified = set()
        self.accessed = {}
        for batches in private.values():
            for batch, files in batches.items():
                for path in files:
                    normalized = PurePosixPath(path)
                    if (str(normalized) != path or normalized.is_absolute() or '..' in normalized.parts
                            or normalized.parts[:2] != ('intake', batch)):
                        raise ValueError('Private arrival must stay in its intake batch')

    def deliver_due(self, now, deliver, *, clock=time.monotonic):
        """The writer confirms installed hashes; failed writes never advance a receipt."""
        added = []
        for batch, offset in self.offsets.items():
            if now < self.activated_at + offset:
                continue
            for actor, batches in self.private.items():
                identity = (actor, batch)
                if identity in self.receipts:
                    continue
                files = batches[batch]
                expected = file_hashes(files)
                observed = deliver(actor, batch, files)
                if observed != expected:
                    raise RuntimeError(f'Private arrival hash mismatch: {actor}/{batch}')
                receipt = {'actor': actor, 'batch': batch, 'files': expected,
                           'offset_seconds': offset, 'delivered_at_monotonic': clock(),
                           'scheduled_at_monotonic': self.activated_at + offset,
                           'source': 'business_intake'}
                self.receipts[identity] = receipt
                added.append(receipt)
        return added

    def pending_notice(self, actor, *, active=False):
        if actor not in self.private:
            raise ValueError('Unknown station')
        if active:
            return None
        batches = [batch for batch, offset in self.offsets.items()
                   if offset and (actor, batch) in self.receipts and (actor, batch) not in self.notified and (actor, batch) not in self.accessed]
        if not batches:
            return None
        paths = [f'/workspace/{path}' for batch in batches for path in sorted(self.private[actor][batch])]
        return {'actor': actor, 'batches': batches,
                'text': 'New intake files are available:\n' + '\n'.join(paths)}

    def acknowledge_notice(self, notice):
        actor, batches = notice['actor'], notice['batches']
        if not batches or any((actor, batch) not in self.receipts or not self.offsets[batch] for batch in batches):
            raise ValueError('Notice does not identify delivered private updates')
        self.notified.update((actor, batch) for batch in batches)

    def acknowledge_reads(self, actor, reads):
        """Omit arrival-only notices once each delivered file was accessed.

        This is scheduling evidence, not a business-completion judgment.
        """
        if actor not in self.private:
            raise ValueError('Unknown station')
        added = []
        for batch, offset in self.offsets.items():
            identity = (actor, batch)
            if not offset or identity not in self.receipts or identity in self.notified or identity in self.accessed:
                continue
            hashes = self.receipts[identity]['files']
            selected = {path: reads.get('/workspace/' + path) for path in hashes}
            if not all(receipt and receipt.get('bytes_read', 0) > 0
                       and receipt.get('delivered_file_sha256') == hashes[path]
                       for path, receipt in selected.items()):
                continue
            record = {'actor': actor, 'batch': batch, 'reads': selected,
                      'reason': 'delivered_files_already_accessed',
                      'claim_scope': 'arrival_awareness_not_completion'}
            self.accessed[identity] = record
            added.append(record)
        return added

    @property
    def updates_accounted(self):
        return len(self.notified | set(self.accessed)) == len(self.private) * (len(self.offsets) - 1)

    @property
    def all_delivered(self):
        return len(self.receipts) == len(self.private) * len(self.offsets)
