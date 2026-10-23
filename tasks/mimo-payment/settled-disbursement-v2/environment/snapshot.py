import json,sqlite3,hashlib,base64
from pathlib import Path
out={'files':{},'databases':{}}
for p in sorted(Path('/work/workspace').rglob('*')):
 if p.is_file() and not p.is_symlink():out['files'][str(p.relative_to('/work/workspace'))]=hashlib.sha256(p.read_bytes()).hexdigest()
for p in sorted(Path('/work/system').rglob('state.db')):
 con=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True);con.row_factory=sqlite3.Row
 out['databases'][str(p.relative_to('/work/system'))]={t:sorted([dict(r) for r in con.execute('SELECT * FROM "'+t.replace('"','""')+'"')],key=lambda x:json.dumps(x,sort_keys=True)) for t, in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")};con.close()
print(json.dumps(out,ensure_ascii=False))
