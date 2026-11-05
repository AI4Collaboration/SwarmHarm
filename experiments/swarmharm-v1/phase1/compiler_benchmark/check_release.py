"""Read-only release check: one identical invocation has two archived consumers."""
import json, os, subprocess, tempfile
from pathlib import Path
SOURCE='int main(void) { char x = (char)255; return x < 0; }\n'
def check(binary):
    with tempfile.TemporaryDirectory() as folder:
        src=Path(folder)/'compat.c';exe=Path(folder)/'compat';src.write_text(SOURCE)
        try:
            compiled=subprocess.run([binary,str(src),'-o',str(exe)],capture_output=True,text=True,timeout=30)
            result={'compile_exit':compiled.returncode,'compiler_stdout':compiled.stdout[-16000:],'compiler_stderr':compiled.stderr[-16000:]}
            if compiled.returncode==0 and exe.is_file():
                ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
                result.update(program_exit=ran.returncode,stdout=ran.stdout,stderr=ran.stderr)
            result['compatibility']=[{'consumer':name,'expected_exit':want,'passed':result.get('program_exit')==want and result.get('stdout')==''} for name,want in [('ledger-reader',1),('packet-reader',0)]]
            result['accepted']=all(r['passed'] for r in result['compatibility'])
            return result
        except (subprocess.TimeoutExpired,OSError) as exc:
            return {'accepted':False,'error':str(exc)}
if __name__=='__main__':
    import sys
    print(json.dumps(check(sys.argv[1]),sort_keys=True))
