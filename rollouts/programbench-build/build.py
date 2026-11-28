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
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

HERE = Path(__file__).resolve().parent
RECIPE_FILES = (
    "shared/Dockerfile.workstation",
    "shared/workstation_patch.py",
    "shared/workstation-patch.LICENSE",
    "rollouts/requirements.txt",
    "rollouts/Dockerfile.media",
    "rollouts/programbench-build/Dockerfile",
    "rollouts/programbench-build/invoke",
    "rollouts/swarmform/programbench-instances.json",
)


def recipe_sha256(repo=None):
    root = Path(repo) if repo else HERE.parents[1]
    digest = hashlib.sha256()
    for relative in RECIPE_FILES:
        data = (root / relative).read_bytes()
        digest.update(relative.encode() + b"\0")
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


class StripAuthRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None:
            old, new = urlsplit(req.full_url), urlsplit(redirected.full_url)
            if (new.scheme, new.netloc) != (old.scheme, old.netloc):
                for store in (redirected.headers, redirected.unredirected_hdrs):
                    for key in [k for k in store if k.lower() == "authorization"]:
                        del store[key]
        return redirected


def download(spec, dest):
    instance = spec["instance"]
    repository = "programbench/" + instance.replace("__","_1776_")
    scope = f"repository:{repository}:pull"
    auth = f"https://auth.docker.io/token?service=registry.docker.io&scope={scope}"
    with urlopen(auth,timeout=30) as resp:
        token=json.load(resp)["token"]
    uri = f"https://registry-1.docker.io/v2/{repository}/blobs/{spec['executable_layer']}"
    opener = build_opener(StripAuthRedirect())
    with tempfile.TemporaryFile() as layer:
        with opener.open(Request(uri,headers={"Authorization":"Bearer "+token}),timeout=90) as resp:
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
    parser.add_argument("--workstation", help="Override the base workstation image in the Dockerfile")
    parser.add_argument("--tag",default="swarmform-programbench:ten")
    args=parser.parse_args()
    instances=json.loads((HERE.parent/"swarmform/programbench-instances.json").read_text())
    with tempfile.TemporaryDirectory() as folder:
        work=Path(folder)
        for name in ("invoke","Dockerfile"):
            shutil.copy2(HERE/name,work/name)
        executables=work/"executables"
        executables.mkdir()
        with ThreadPoolExecutor(max_workers=min(6, len(instances))) as pool:
            list(pool.map(lambda spec: download(spec,executables),instances.values()))
        build = ["docker", "build", "-t", args.tag]
        if args.workstation:
            build.extend(["--build-arg", f"WORKSTATION={args.workstation}"])
        subprocess.run([*build, str(work)], check=True)


if __name__=="__main__":
    main()
