import argparse
import json
import os
from pathlib import Path
import subprocess


PARAMETER = "/swarmharm/swh119/operator-handoff"


def aws(*args):
    result = subprocess.run(["aws", "--profile", "eurosafeai", "--region", "eu-central-1", "--output", "json", "--no-cli-pager", *args],
        check=True, capture_output=True, text=True)
    return json.loads(result.stdout) if result.stdout.strip() else {}


def private_file(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    with open(path, "w", opener=lambda filename, flags: os.open(filename, flags, 0o600)) as stream:
        stream.write(value)
    path.chmod(0o600)


def publish(args):
    assert aws("sts", "get-caller-identity")["Account"] == "906513713427"
    value = {
        "campaign": "SWH-119",
        "meta_host": "63.186.173.73",
        "meta_ssh_key": args.meta_key.read_text(),
        "axonhub": json.loads(args.axonhub_key.read_text()),
    }
    path = args.directory.resolve() / "parameter-value.json"
    private_file(path, json.dumps(value))
    result = aws("ssm", "put-parameter", "--name", PARAMETER, "--type", "SecureString", "--overwrite", "--value", "file://" + str(path))
    returned = json.loads(aws("ssm", "get-parameter", "--name", PARAMETER, "--with-decryption")["Parameter"]["Value"])
    assert returned == value
    print(json.dumps({"parameter": PARAMETER, "version": result["Version"], "retrieval": "verified"}))


def retrieve(args):
    assert aws("sts", "get-caller-identity")["Account"] == "906513713427"
    value = json.loads(aws("ssm", "get-parameter", "--name", PARAMETER, "--with-decryption")["Parameter"]["Value"])
    assert value["campaign"] == "SWH-119"
    directory = args.directory.resolve()
    private_file(directory / "swh6-ed25519", value["meta_ssh_key"])
    private_file(directory / "axonhub-key.json", json.dumps(value["axonhub"], indent=2) + "\n")
    print(json.dumps({"parameter": PARAMETER, "directory": str(directory), "retrieval": "verified"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("publish", "retrieve"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--meta-key", type=Path)
    parser.add_argument("--axonhub-key", type=Path)
    args = parser.parse_args()
    if args.action == "publish":
        assert args.meta_key and args.axonhub_key
        publish(args)
    else:
        retrieve(args)
