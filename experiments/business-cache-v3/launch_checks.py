"""Process ownership proof without model/provider access."""
from hashlib import sha256
import json,os
from pathlib import Path
import subprocess,sys,tempfile,time,unittest
import launch

class Checks(unittest.TestCase):
    def test_child_survives_launcher_exit_and_duplicate_launch_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);reg=root/'registration.json';reg.write_text(json.dumps({'code_hashes':{}}));(root/'registration-seal.json').write_text(json.dumps({'sha256':sha256(reg.read_bytes()).hexdigest()}))
            module=str(Path(launch.__file__).resolve());marker=root/'finished.json'
            child='import time,json,os;from pathlib import Path;time.sleep(.3);Path('+repr(str(marker))+').write_text(json.dumps({"pid":os.getpid(),"parent":os.getppid()}))'
            parent='import importlib.util;from pathlib import Path;s=importlib.util.spec_from_file_location("owned_launcher",'+repr(module)+');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);print(m.launch(Path('+repr(str(root))+'),command=['+repr(sys.executable)+',"-c",'+repr(child)+']))'
            completed=subprocess.run([sys.executable,'-c',parent],capture_output=True,check=True,timeout=10);pid=int(completed.stdout)
            for _ in range(50):
                if marker.exists():break
                time.sleep(.1)
            self.assertTrue(marker.exists());self.assertEqual(json.loads(marker.read_text())['pid'],pid);self.assertTrue(json.loads((root/'launcher.json').read_text())['new_session'])
            with self.assertRaises(AssertionError):launch.launch(root,command=[sys.executable,'-c','pass'])

if __name__=='__main__':unittest.main(verbosity=2)
