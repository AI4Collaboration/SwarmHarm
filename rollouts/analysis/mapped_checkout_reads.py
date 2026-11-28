"""Bind a displayed project file to the earlier pinned read that created a local copy."""
import base64
from collections import defaultdict
import json
from pathlib import Path

from mapped_processes import log_lines, STDOUT_WRITE, unhex
from swarmform.read_observer import observed_reads


def displayed_copies(case, receipts, origin, deadline, events):
    by_actor = defaultdict(lambda: defaultdict(list))
    for r in receipts:
        path = r.get('saved_to')
        if isinstance(path, str) and Path(path).is_absolute():
            by_actor[r['actor']][path].append(r)
    for actor, paths in by_actor.items():
        archive = case / 'reads' / actor
        bindings = json.loads((archive / 'origins.json').read_bytes())
        index = json.loads(sorted(archive.glob('[0-9]*.json'))[-1].read_bytes())['files']
        outputs = {e['call_id']:e for e in events(case / (actor+'.jsonl.gz'), resolve_blobs=False)
                   if e['kind']=='tool_result' and 0<=e['s']<=deadline}
        encoded_paths = {pattern for path in paths for pattern in
                         (path.encode(), b''.join(b'\\x%02x' % byte for byte in path.encode()))}
        for trace, target in index.items():
            native = bindings.get(trace, {}).get('native_call') or {}
            cid = native.get('call_id')
            if native.get('actor')!=actor or cid not in outputs:
                continue
            reply = outputs[cid]
            stdout = reply['result'].get('stdout','')
            if not isinstance(stdout, str) or not stdout or all(r['seconds']>=reply['s'] for rs in paths.values() for r in rs):
                continue
            pending = {}
            for line, raw in enumerate(log_lines(archive,target),1):
                fields=raw.split(None,2)
                if len(fields)!=3 or not fields[0].isdigit():
                    continue
                pid, stamp, call = fields
                if call.startswith(b'(+'):
                    call = call.partition(b') ')[2]
                if call.startswith((b'+++',b'execve(')):
                    pending.pop(pid,None)
                if call.startswith((b'read(',b'pread64(')) and any(
                        pat in call.partition(b'>')[0] for pat in encoded_paths):
                    for seen in observed_reads(raw.decode(errors='replace')):
                        candidates = [r for r in paths.get(seen['path'],()) if r['sha256']==seen['sha256'] and
                                      r['seconds']<=float(stamp)-origin<=reply['s']]
                        if not candidates or len({(r['author'],r['name'],r['version']) for r in candidates})!=1:
                            continue
                        data=base64.b64decode(seen['data_base64'])
                        try:text=data.decode('utf-8')
                        except UnicodeError:continue
                        if text and text in stdout:
                            pending[pid]=(max(candidates,key=lambda x:x['seconds']),text,line)
                if pid not in pending or not call.startswith(b'write(1<'):
                    continue
                match=STDOUT_WRITE.search(call)
                if not match or match[2]!=match[3] or len(match[1])!=int(match[3])*4:
                    continue
                first,text,read_line=pending[pid]
                if unhex(match[1])!=text.encode():
                    continue
                del pending[pid]
                yield dict(actor=actor,author=first['author'],name=first['name'],version=first['version'],
                           sha256=first['sha256'],operation='read',call_id=cid,seconds=float(stamp)-origin,
                           via='mapped_checkout_content',returned_s=reply['s'],text=text[:420],local_path=first['saved_to'],
                           materialized_by=first['call_id'],trace_file=trace,read_line=read_line,receipt_line=line)
