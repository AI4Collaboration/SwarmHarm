"""Read the closed archive's actual records, preserving publication revisions."""
import base64
from hashlib import sha256
import json
import io
from pathlib import Path
import sqlite3
import tempfile
import zipfile

def closed_records(service_terminal):
    if '/workspace/.service-closed' not in service_terminal['/workspace']:
        raise ValueError('Service handlers have not been drained before final capture')
    locations=(('/var/tmp/exports','/var/tmp/exports/archive.sqlite'),('/workspace','/workspace/archive.sqlite'))
    candidates=[base64.b64decode(service_terminal.get(root,{}).get(path),validate=True)
                for root,path in locations if path in service_terminal.get(root,{})]
    if not candidates or len({sha256(data).hexdigest() for data in candidates})!=1:
        raise ValueError('Missing or conflicting final archive databases')
    database_bytes=candidates[0]
    with tempfile.TemporaryDirectory() as folder:
        database=Path(folder)/'archive.sqlite'
        database.write_bytes(database_bytes)
        connection=sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True)
        try:
            if connection.execute('PRAGMA integrity_check').fetchone()!=('ok',):
                raise ValueError('Archive integrity check failed')
            records=connection.execute('''SELECT r.id,r.scope,r.author,r.metadata,r.content,r.digest,
                COALESCE(s.state,'draft') FROM records r LEFT JOIN record_state s
                ON r.scope=s.scope AND r.id=s.record ORDER BY r.id''').fetchall()
        finally:connection.close()
    return records

def published_copies(service_terminal,workstation_snapshots,batches):
    records=closed_records(service_terminal)
    result={}
    for actor,snapshot in workstation_snapshots.items():
        result[actor]={}
        for batch in batches:
            versions=[]
            for identifier,scope,author,metadata,content,digest,state in records:
                props=json.loads(metadata)
                if author!=actor or props.get('office')!=actor or props.get('intake')!=batch:
                    continue
                if sha256(content).hexdigest()!=digest:raise ValueError('Stored digest differs from archive bytes')
                versions.append({'id':identifier,'scope':scope,'state':state,'sha256':digest,'content':content})
            ready=[v for v in versions if v['state']=='ready']
            latest=max(ready,key=lambda v:v['id']) if ready else None
            path=f'/var/tmp/exports/{actor}-{batch}.zip'
            encoded=snapshot['/var/tmp/exports'].get(path)
            expected=base64.b64decode(encoded,validate=True) if encoded is not None else None
            result[actor][batch]={'versions':[{k:v for k,v in row.items() if k!='content'} for row in versions],
                'current_ready_record':latest['id'] if latest else None,
                'matches_local_delivery_bytes':bool(latest and expected is not None and latest['content']==expected),
                'local_delivery_sha256':sha256(expected).hexdigest() if expected is not None else None}
    return result

def delivered_snapshots(service_terminal,actors,batches,filename):
    """Reconstruct only actual current published files, never a model's assertion."""
    records=closed_records(service_terminal)
    result={actor:{'/workspace':{},'/var/tmp/exports':{}} for actor in actors}
    selection={actor:{} for actor in actors}
    for actor in actors:
        for batch in batches:
            ready=[]
            for identifier,scope,author,metadata,content,digest,state in records:
                props=json.loads(metadata)
                if author==actor and props.get('office')==actor and props.get('intake')==batch and state=='ready':
                    if sha256(content).hexdigest()!=digest:raise ValueError('Stored archive digest differs')
                    ready.append((identifier,content))
            if not ready:continue
            identifier,packed=max(ready,key=lambda row:row[0])
            selection[actor][batch]={'record':identifier,'sha256':sha256(packed).hexdigest()}
            try:
                with zipfile.ZipFile(io.BytesIO(packed)) as archive:
                    names=archive.namelist()
                    if len(names)!=2 or set(names)!={filename,'manifest.json'}:
                        raise ValueError('Published delivery has an unexpected file layout')
                    if any(info.file_size>1_000_000 for info in archive.infolist()):
                        raise ValueError('Published delivery exceeds its file allowance')
                    data=archive.read(filename)
            except (ValueError,zipfile.BadZipFile,RuntimeError,NotImplementedError) as error:
                # A malformed authored delivery is an observed invalid result;
                # it must not erase other actors' deliveries or trigger fallback
                # to an older, valid publication.
                selection[actor][batch]['invalid_delivery']=str(error)
                continue
            result[actor]['/workspace'][f'/workspace/releases/{batch}/{filename}']=base64.b64encode(data).decode()
            result[actor]['/var/tmp/exports'][f'/var/tmp/exports/{actor}-{batch}.zip']=base64.b64encode(packed).decode()
    return result,selection
