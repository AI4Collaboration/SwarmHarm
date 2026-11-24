"""Build the optional workstation from the ten checksum-pinned upstream executables."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent


def download(spec, dest):
    instance = spec["instance"]
    repository = "programbench/" + instance.replace("__","_1776_")
    scope = f"repository:{repository}:pull"
    auth = f"https://auth.docker.io/token?service=registry.docker.io&scope={scope}"
    with urlopen(auth,timeout=30) as resp:
        token=json.load(resp)["token"]
    uri = f"https://registry-1.docker.io/v2/{repository}/blobs/{spec['executable_layer']}"
    with tempfile.TemporaryFile() as layer:
        with urlopen(Request(uri,headers={"Authorization":"Bearer "+token}),timeout=90) as resp:
            shutil.copyfileobj(resp,layer)
        layer.seek(0)
        if "sha256:"+hashlib.file_digest(layer,"sha256").hexdigest() != spec["executable_layer"]:
            raise ValueError(f"Layer checksum mismatch for {instance}")
        layer.seek(0)
        with tarfile.open(fileobj=layer,mode="r:gz") as tar:
            member=next((x for x in tar if x.isfile() and x.name.removeprefix("./")=="workspace/executable"),None)
            if member is None:
                raise ValueError(f"No ProgramBench executable in {instance}")
            output=dest/instance
            with tar.extractfile(member) as reference,output.open("wb") as out:
                shutil.copyfileobj(reference,out)
        with output.open("rb") as f:
            if hashlib.file_digest(f,"sha256").hexdigest()!=spec["executable_sha256"]:
                raise ValueError(f"Executable checksum mismatch for {instance}")
        output.chmod(0o555)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workstation",default="swarmform-media:360a402-toolchain")
    parser.add_argument("--tag",default="swarmform-programbench:ten")
    args=parser.parse_args()
    instances=json.loads((HERE.parent/"swarmform/programbench-instances.json").read_text())
    with tempfile.TemporaryDirectory() as folder:
        work=Path(folder)
        for name in ("invoke","Dockerfile"):
            shutil.copy2(HERE/name,work/name)
        executables=work/"executables"
        executables.mkdir()
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda spec: download(spec,executables),instances.values()))
        subprocess.run(["docker","build","--build-arg",f"WORKSTATION={args.workstation}","-t",args.tag,str(work)],check=True)


if __name__=="__main__":
    main()
