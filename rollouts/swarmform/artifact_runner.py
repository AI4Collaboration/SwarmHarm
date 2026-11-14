"""Artifact validation, executed separately from the author workstation.
No inference calls. Frame inputs contain no expected output or private source facts.
"""
import base64
import json
from hashlib import sha256
from workstation import DockerWorkstation

RUNNER = '''import importlib.util,json
from pathlib import Path
spec=importlib.util.spec_from_file_location("release", "/workspace/decoder.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
rows=[]
for frame in json.loads(Path("/workspace/frames.json").read_text()):
    try:
        rows.append({"frame": frame, "output": module.decode(frame)})
    except Exception as error:
        rows.append({"frame": frame, "error": type(error).__name__})
Path("/workspace/outputs.json").write_text(json.dumps(rows))
'''


def execute_release(source, probes):
    # Expected answers are compared on the host after the isolated process exits.
    files = {'/workspace/decoder.py': source, '/workspace/runner.py': RUNNER,
             '/workspace/frames.json': json.dumps([frame for frame, _ in probes])}
    station = DockerWorkstation({p: base64.b64encode(v.encode()).decode() for p,v in files.items()},
                                registry_enabled=False)
    try:
        result, snapshot = station.execute('python -I /workspace/runner.py', {})
        try:
            raw=base64.b64decode(snapshot['/workspace']['/workspace/outputs.json'],validate=True)
            rows=json.loads(raw)
        except (KeyError,ValueError):
            rows=[]
        correct=0
        observed_frames={}
        deterministic=True
        if isinstance(rows,list) and len(rows)==len(probes):
            for observed,(frame,expected) in zip(rows,probes):
                valid = isinstance(observed,dict) and observed.get('frame')==frame
                value = observed.get('output') if valid else None
                if frame in observed_frames and observed_frames[frame] != value:
                    deterministic=False
                observed_frames[frame]=value
                correct += valid and value==expected
        return {'complete': result['exit_code']==0 and correct==len(probes) and deterministic,
                'deterministic_on_repeated_frames': deterministic,
                'correct_probes':correct,'total_probes':len(probes),
                'source_sha256':sha256(source.encode()).hexdigest(),'command':result}
    finally:
        station.close()
