"""Package a dated release for the business export queue."""
from hashlib import sha256
import json
from pathlib import Path
import sys
import zipfile


def main():
    delivery=json.loads(Path('/workspace/delivery.json').read_text())
    if len(sys.argv)!=2 or sys.argv[1] not in delivery['batches']:
        raise SystemExit('Choose an intake listed in delivery.json.')
    batch=sys.argv[1]
    path=Path('/workspace/releases')/batch/delivery['filename']
    content=path.read_bytes()
    if len(content)>1_000_000:
        raise SystemExit('The release exceeds the delivery file allowance.')
    if not content.strip():
        raise SystemExit('The release file is empty.')
    exports=Path('/var/tmp/exports');exports.mkdir(parents=True,exist_ok=True)
    destination=exports/(delivery['office']+'-'+batch+'.zip')
    metadata={'office':delivery['office'],'batch':batch,'file':delivery['filename'],
              'sha256':sha256(content).hexdigest()}
    pending=destination.with_suffix('.pending')
    with zipfile.ZipFile(pending,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(delivery['filename'],content)
        archive.writestr('manifest.json',json.dumps(metadata,sort_keys=True)+'\n')
    pending.replace(destination)
    print(json.dumps({'package':str(destination),'sha256':sha256(destination.read_bytes()).hexdigest()}))


if __name__=='__main__':main()
