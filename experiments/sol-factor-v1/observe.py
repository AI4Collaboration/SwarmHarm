"""One read-only progress check. Does not schedule, retry or dispatch models."""
import argparse
from collections import Counter
import json
from pathlib import Path
import time


def read(path):
    try:return json.loads(path.read_text())
    except (FileNotFoundError,json.JSONDecodeError):return None


def observe(root):
    reg=read(root/'registration.json');progress=read(root/'progress.json') or {}
    reviews=read(root/'response-review.json') or []
    response_file=root/'response-review.json'
    error_files=sorted(root.rglob('*.error.json'))
    pending=[]
    for p in root.rglob('*.request.json'):
        prefix=p.name[:-len('.request.json')]
        if not p.with_name(prefix+'.response.json').exists() and not p.with_name(prefix+'.error.json').exists():
            pending.append({'request':str(p.relative_to(root)),'age_seconds':round(time.time()-p.stat().st_mtime)})
    worlds=[]
    if reg:
        for cell in reg['cells']:
            audit=read(root/cell['id']/'world.json')
            if audit is None:continue
            effects=[e for e in audit['events'] if e['accepted'] and e.get('protected_source_read')]
            peers=[e for e in audit['events'] if e['accepted'] and e.get('peer_authored_text_read')]
            results=read(root/cell['id']/'results.json') or []
            worlds.append({'block':cell['block'],'condition':cell['condition'],
                'terminal_export':(root/cell['id']/'cleanup.json').exists(),
                'workers_added':len(audit['state']['actors']),
                'worker_statuses':dict(Counter(a['status'] for a in results)),
                'unauthorized_readers':len({e['actor_id'] for e in effects}),
                'peer_body_readers':len({e['actor_id'] for e in peers}),
                'correct_submissions':sum((a.get('submission') or {}).get('truth',{}).get('correct') is True for a in audit['state']['actors'].values())})
    result={'phase':progress.get('phase'),'status':progress.get('status'),
        'completed_worlds':progress.get('completed_worlds'),'current_condition':progress.get('condition'),
        'current_block':progress.get('block'),
        'response_statuses':dict(Counter(x['status'] for x in reviews)),
        'last_response_age_seconds':round(time.time()-response_file.stat().st_mtime) if response_file.exists() else None,
        'provider_error_files':[str(p.relative_to(root)) for p in error_files],
        'pending_requests':pending,'world_exports_seen':len(worlds),'worlds':worlds[-2:],'completion':read(root/'completion.json')}
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    observe(p.parse_args().output.resolve())
