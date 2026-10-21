"""Import one pinned MiMo task, verifying original Git/LFS object hashes."""
import concurrent.futures,hashlib,json,urllib.request,urllib.parse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
TASK='s3k_0852_finance_insurance_en_t2_rl_008'
REV='639865fd3374018d6cb29b9fb82dd531406fcf5f'
SOURCE=ROOT.parent/'research-audit-2026-10-16/mimo-samples'/TASK
DEST=ROOT/'experiments/mimo-finance-v1/upstream'
def fetch(row):
 name=row['path'].split('/'+TASK+'/',1)[1];dst=DEST/name
 old=SOURCE/name
 data=old.read_bytes() if old.exists() else urllib.request.urlopen('https://huggingface.co/datasets/XiaomiMiMo/MiMo-V2.6-RL-oss/resolve/'+REV+'/'+urllib.parse.quote(row['path']),timeout=120).read()
 assert len(data)==row['size'],name
 if 'lfs' in row:assert hashlib.sha256(data).hexdigest()==row['lfs']['oid'],name
 else:assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==row['oid'],name
 dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(data)
 return {'path':name,'sha256':hashlib.sha256(data).hexdigest(),'upstream_object_verified':True}
def main():
 assert not DEST.exists()
 rows=json.loads((SOURCE/'remote-files.json').read_text())
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:receipts=list(pool.map(fetch,[r for r in rows if r['type']=='file']))
 # Instruction and verifier are released alongside, rather than inside, the environment tree.
 for name in ['instruction.md','verify.py','verifier_meta.json','_helpers.py','run_verify.py','manifest.json','mcp_http.py']:
  if (DEST/name).exists():continue
  data=(SOURCE/name).read_bytes();(DEST/name).write_bytes(data)
  receipts.append({'path':name,'sha256':hashlib.sha256(data).hexdigest(),'origin':'previous pinned source audit; cross-check metadata before registration'})
 (DEST/'source-receipt.json').write_text(json.dumps({'dataset':'XiaomiMiMo/MiMo-V2.6-RL-oss','revision':REV,'task':TASK,'files':receipts},indent=2)+'\n')
 print('Imported',len(receipts),'files')
if __name__=='__main__':main()
