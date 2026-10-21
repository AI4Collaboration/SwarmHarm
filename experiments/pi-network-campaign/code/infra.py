import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import uuid


ROLES = ("controller", "proxy", "runtime")
ACCOUNT = "906513713427"
REGION = "eu-central-1"
VPC = "vpc-0dc6260011176dcae"
SUBNET = "subnet-0f9b3bc5da2c0c635"
ADMIN_CIDR = "195.176.112.0/24"
TEMPLATES = Path(__file__).resolve().parent


def run(argv, **kwargs):
    result = subprocess.run(argv, text=True, **kwargs)
    if result.returncode and result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    result.check_returncode()
    return result


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class Trial:
    def __init__(self, state, profile="eurosafeai"):
        self.path = Path(state).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.parent.chmod(0o700)
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.profile = self.data.get("profile", profile)

    def save(self):
        self.data["updated_at"] = now()
        pending = self.path.with_suffix(".pending")
        with open(pending, "w", opener=lambda p, f: os.open(p, f, 0o600)) as stream:
            json.dump(self.data, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        pending.chmod(0o600)
        pending.replace(self.path)

    def aws(self, service, operation, *args):
        result = run(["aws", "--profile", self.profile, "--region", REGION,
                      "--output", "json", "--no-cli-pager", service, operation,
                      *map(str, args)], capture_output=True)
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def identity(self):
        identity = self.aws("sts", "get-caller-identity")
        assert identity["Account"] == ACCOUNT, identity["Account"]
        return identity

    def tags(self, role):
        return [{"Key": "issue", "Value": "SWH-119"},
                {"Key": "trial", "Value": self.data["trial"]},
                {"Key": "campaign_owner", "Value": self.data["owner"]},
                {"Key": "role", "Value": role}]

    def specs(self, resource, role):
        return json.dumps([{"ResourceType": resource, "Tags": self.tags(role)}])

    def expect_owner(self, tags):
        values = {item["Key"]: item["Value"] for item in tags}
        assert values["issue"] == "SWH-119", values
        assert values["trial"] == self.data["trial"], values
        assert values["campaign_owner"] == self.data["owner"], values

    def phase(self, value):
        self.data["phase"] = value
        self.data.setdefault("phase_history", []).append({"phase": value, "at": now()})
        self.save()

    def permission(self, protocol, port, cidr=None, group=None):
        result = {"IpProtocol": protocol, "FromPort": port, "ToPort": port}
        if cidr:
            result["IpRanges"] = [{"CidrIp": cidr}]
        if group:
            result["UserIdGroupPairs"] = [{"GroupId": group}]
        return result

    def ingress(self, role, permissions):
        self.aws("ec2", "authorize-security-group-ingress", "--group-id",
                 self.data["groups"][role], "--ip-permissions", json.dumps(permissions))

    def create(self, trial, ami=None):
        self.identity()
        assert re.fullmatch(r"[a-zA-Z0-9-]{1,40}", trial), trial
        if self.data:
            assert self.data["trial"] == trial
            assert self.data["phase"] != "terminated"
        else:
            self.data = {"trial": trial, "owner": str(uuid.uuid4()), "profile": self.profile,
                         "region": REGION, "account": ACCOUNT, "vpc": VPC, "subnet": SUBNET,
                         "created_at": now(), "instances": {}, "groups": {}}
            self.phase("creating")
        subnet = self.aws("ec2", "describe-subnets", "--subnet-ids", SUBNET)["Subnets"][0]
        assert subnet["VpcId"] == VPC
        assert subnet["AvailableIpAddressCount"] >= 3
        if ami:
            image = self.aws("ec2", "describe-images", "--image-ids", ami)["Images"][0]
            assert image["OwnerId"] == "099720109477"
            assert image["Architecture"] == "x86_64"
            assert image["Name"].startswith("ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-")
            assert image["State"] == "available"
            if "ami" in self.data:
                assert self.data["ami"] == ami
            else:
                self.data["ami"] = ami
                self.save()
        if "ami" not in self.data:
            images = self.aws("ec2", "describe-images", "--owners", "099720109477",
                              "--filters", "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*",
                              "Name=state,Values=available", "Name=architecture,Values=x86_64")["Images"]
            self.data["ami"] = max(images, key=lambda item: item["CreationDate"])["ImageId"]
            self.save()
        key = self.path.parent / "operator-ed25519"
        if "key_name" not in self.data:
            if not key.exists():
                run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)])
            self.data["key_name"] = f"swh119-{trial}-{self.data['owner'][:8]}"
            self.data["key_file"] = str(key)
            self.save()
        existing_keys = self.aws("ec2", "describe-key-pairs", "--filters",
                                 f"Name=key-name,Values={self.data['key_name']}")["KeyPairs"]
        if existing_keys:
            self.expect_owner(existing_keys[0]["Tags"])
        else:
            self.aws("ec2", "import-key-pair", "--key-name", self.data["key_name"],
                     "--public-key-material", f"fileb://{key}.pub",
                     "--tag-specifications", self.specs("key-pair", "operator"))
        for role in ROLES:
            if role not in self.data["groups"]:
                candidates = self.aws("ec2", "describe-security-groups", "--filters",
                                      f"Name=tag:campaign_owner,Values={self.data['owner']}",
                                      f"Name=tag:role,Values={role}")["SecurityGroups"]
                assert len(candidates) <= 1
                if candidates:
                    group = candidates[0]
                    self.expect_owner(group["Tags"])
                else:
                    group = self.aws("ec2", "create-security-group", "--group-name",
                                     f"swh119-{trial}-{role}-{self.data['owner'][:8]}", "--description",
                                     f"SWH-119 {trial} {role}", "--vpc-id", VPC,
                                     "--tag-specifications", self.specs("security-group", role))
                self.data["groups"][role] = group["GroupId"]
                self.save()
        if not self.data.get("ingress_ready"):
            for role in ROLES:
                group = self.aws("ec2", "describe-security-groups", "--group-ids", self.data["groups"][role])["SecurityGroups"][0]
                if group["IpPermissions"]:
                    self.aws("ec2", "revoke-security-group-ingress", "--group-id", group["GroupId"],
                             "--ip-permissions", json.dumps(group["IpPermissions"]))
                self.ingress(role, [self.permission("tcp", 22, cidr=ADMIN_CIDR)])
            self.ingress("controller", [self.permission("tcp", port, cidr="0.0.0.0/0") for port in (80, 443)])
            self.ingress("proxy", [self.permission("tcp", 3128, group=self.data["groups"]["runtime"])])
            self.data["ingress_ready"] = True
            self.save()
        for role in ROLES:
            if role in self.data["instances"]:
                continue
            tags = [{"ResourceType": resource, "Tags": self.tags(role)} for resource in ("instance", "volume")]
            network = [{"DeviceIndex": 0, "SubnetId": SUBNET, "Groups": [self.data["groups"][role]],
                        "AssociatePublicIpAddress": True, "DeleteOnTermination": True}]
            launch = self.aws("ec2", "run-instances", "--image-id", self.data["ami"],
                              "--instance-type", "t3.small", "--count", "1", "--key-name", self.data["key_name"],
                              "--network-interfaces", json.dumps(network), "--credit-specification", "CpuCredits=standard",
                              "--metadata-options", "HttpTokens=required,HttpEndpoint=enabled,HttpPutResponseHopLimit=1",
                              "--block-device-mappings", json.dumps([{"DeviceName": "/dev/sda1", "Ebs": {
                                  "VolumeSize": 20, "VolumeType": "gp3", "Encrypted": True, "DeleteOnTermination": True}}]),
                              "--tag-specifications", json.dumps(tags), "--client-token", f"{self.data['owner']}-{role}")
            self.data["instances"][role] = {"id": launch["Instances"][0]["InstanceId"]}
            self.save()
        ids = [host["id"] for host in self.data["instances"].values()]
        self.aws("ec2", "wait", "instance-running", "--instance-ids", *ids)
        self.refresh()
        self.aws("ec2", "wait", "instance-status-ok", "--instance-ids", *ids)
        if self.data["phase"] == "creating":
            self.phase("created")

    def refresh(self):
        ids = [host["id"] for host in self.data["instances"].values()]
        reservations = self.aws("ec2", "describe-instances", "--instance-ids", *ids)["Reservations"]
        for reservation in reservations:
            for host in reservation["Instances"]:
                self.expect_owner(host["Tags"])
                role = next(role for role, value in self.data["instances"].items() if value["id"] == host["InstanceId"])
                self.data["instances"][role].update(public_ip=host.get("PublicIpAddress"),
                                                      private_ip=host.get("PrivateIpAddress"),
                                                      state=host["State"]["Name"],
                                                      volumes=[item["Ebs"]["VolumeId"] for item in host.get("BlockDeviceMappings", [])])
        self.save()

    def ssh_options(self):
        return ["-i", self.data["key_file"], "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
                "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=4",
                "-o", "StrictHostKeyChecking=accept-new", "-o",
                f"UserKnownHostsFile={self.path.parent / 'known_hosts'}"]

    def ssh(self, role, command, capture=False):
        return run(["ssh", *self.ssh_options(), f"ubuntu@{self.data['instances'][role]['public_ip']}", command],
                   capture_output=capture)

    def copy(self, role, source, destination):
        assert re.fullmatch(r"/[a-zA-Z0-9_./-]+", destination), destination
        return run(["scp", *self.ssh_options(), str(source),
                    f"ubuntu@{self.data['instances'][role]['public_ip']}:{destination}"])

    def script(self, role, name, *args):
        self.ssh(role, "mkdir -p /home/ubuntu/campaign-bootstrap && chmod 700 /home/ubuntu/campaign-bootstrap")
        destination = f"/home/ubuntu/campaign-bootstrap/{name}"
        self.copy(role, TEMPLATES / name, destination)
        return self.ssh(role, shlex.join(["sudo", "bash", destination, *map(str, args)]))

    def base(self, pi_version, multica_version, node_package_version=""):
        assert self.data["phase"] in ("created", "base-configured")
        self.data["versions"] = {"pi": pi_version, "multica": multica_version, "node_major": 22}
        self.save()
        for role in ROLES:
            self.ssh(role, "sudo cloud-init status --wait")
            self.script(role, "infra-common.sh")
        self.script("proxy", "infra-proxy.sh", self.data["instances"]["controller"]["public_ip"],
                    self.data["instances"]["runtime"]["private_ip"], ADMIN_CIDR)
        self.script("runtime", "infra-runtime-base.sh", pi_version, multica_version, node_package_version)
        installed_node = self.ssh("runtime", "dpkg-query -W -f='${Version}' nodejs", capture=True).stdout.strip()
        if node_package_version:
            assert installed_node == node_package_version, installed_node
        self.data["versions"]["node_package_version"] = installed_node
        self.phase("base-configured")

    def lockdown(self):
        self.identity()
        assert self.data["phase"] in ("base-configured", "locked", "verified")
        proxy = self.data["instances"]["proxy"]["private_ip"]
        self.script("runtime", "infra-runtime-lockdown.sh", proxy, ADMIN_CIDR)
        group_id = self.data["groups"]["runtime"]
        group = self.aws("ec2", "describe-security-groups", "--group-ids", group_id)["SecurityGroups"][0]
        self.expect_owner(group["Tags"])
        if group["IpPermissionsEgress"]:
            self.aws("ec2", "revoke-security-group-egress", "--group-id", group_id,
                     "--ip-permissions", json.dumps(group["IpPermissionsEgress"]))
        self.aws("ec2", "authorize-security-group-egress", "--group-id", group_id,
                 "--ip-permissions", json.dumps([self.permission("tcp", 3128, group=self.data["groups"]["proxy"]),
                                                 self.permission("udp", 123, cidr="169.254.169.123/32")]))
        self.phase("locked")

    def verify(self):
        self.identity()
        assert self.data["phase"] in ("locked", "verified")
        evidence = {"at": now(), "groups": self.aws("ec2", "describe-security-groups", "--group-ids",
                    *self.data["groups"].values())["SecurityGroups"]}
        ids = [host["id"] for host in self.data["instances"].values()]
        reservations = self.aws("ec2", "describe-instances", "--instance-ids", *ids)["Reservations"]
        hosts = [host for reservation in reservations for host in reservation["Instances"]]
        assert len(hosts) == 3
        volumes = []
        for host in hosts:
            self.expect_owner(host["Tags"])
            role = next(role for role, item in self.data["instances"].items() if item["id"] == host["InstanceId"])
            assert host["InstanceType"] == "t3.small"
            assert host["ImageId"] == self.data["ami"]
            assert host["VpcId"] == VPC and host["SubnetId"] == SUBNET
            assert host["MetadataOptions"]["HttpTokens"] == "required"
            assert host["State"]["Name"] == "running"
            assert host["PublicIpAddress"] == self.data["instances"][role]["public_ip"]
            assert [group["GroupId"] for group in host["SecurityGroups"]] == [self.data["groups"][role]]
            assert len(host["BlockDeviceMappings"]) == 1
            assert host["BlockDeviceMappings"][0]["Ebs"]["DeleteOnTermination"] is True
            volumes.append(host["BlockDeviceMappings"][0]["Ebs"]["VolumeId"])
        credit_specs = self.aws("ec2", "describe-instance-credit-specifications", "--instance-ids", *ids)["InstanceCreditSpecifications"]
        assert len(credit_specs) == 3
        assert all(item["CpuCredits"] == "standard" for item in credit_specs)
        volume_records = self.aws("ec2", "describe-volumes", "--volume-ids", *volumes)["Volumes"]
        for volume in volume_records:
            self.expect_owner(volume["Tags"])
            assert volume["Encrypted"] is True
            assert volume["Size"] == 20 and volume["VolumeType"] == "gp3"
        evidence["instances"] = hosts
        evidence["credit_specifications"] = credit_specs
        evidence["volumes"] = volume_records
        runtime = next(group for group in evidence["groups"] if group["GroupId"] == self.data["groups"]["runtime"])
        rules = runtime["IpPermissionsEgress"]
        assert len(rules) == 2, rules
        tcp = next(rule for rule in rules if rule["IpProtocol"] == "tcp")
        udp = next(rule for rule in rules if rule["IpProtocol"] == "udp")
        assert (tcp["FromPort"], tcp["ToPort"]) == (3128, 3128)
        assert [pair["GroupId"] for pair in tcp["UserIdGroupPairs"]] == [self.data["groups"]["proxy"]]
        assert tcp.get("IpRanges", []) == [] and tcp.get("Ipv6Ranges", []) == []
        assert tcp.get("PrefixListIds", []) == []
        assert (udp["FromPort"], udp["ToPort"]) == (123, 123)
        assert [item["CidrIp"] for item in udp["IpRanges"]] == ["169.254.169.123/32"]
        assert udp.get("Ipv6Ranges", []) == [] and udp.get("UserIdGroupPairs", []) == []
        assert udp.get("PrefixListIds", []) == []
        command = shlex.join(["sudo", "bash", "/home/ubuntu/campaign-bootstrap/infra-verify.sh",
                              self.data["instances"]["proxy"]["private_ip"],
                              self.data["instances"]["controller"]["public_ip"]])
        self.copy("runtime", TEMPLATES / "infra-verify.sh", "/home/ubuntu/campaign-bootstrap/infra-verify.sh")
        evidence["runtime"] = self.ssh("runtime", command, capture=True).stdout
        self.data["verification"] = evidence
        self.phase("verified")
        print(json.dumps(evidence, indent=2))

    def teardown(self):
        self.identity()
        if self.data.get("phase") == "terminated":
            return
        self.phase("tearing-down")
        ids = [host["id"] for host in self.data.get("instances", {}).values()]
        if ids:
            self.refresh()
            active = [host["id"] for host in self.data["instances"].values() if host["state"] != "terminated"]
            volumes = [volume for host in self.data["instances"].values() for volume in host.get("volumes", [])]
            if active:
                self.aws("ec2", "terminate-instances", "--instance-ids", *active)
                self.aws("ec2", "wait", "instance-terminated", "--instance-ids", *active)
            if volumes:
                self.aws("ec2", "wait", "volume-deleted", "--volume-ids", *volumes)
            self.refresh()
        for role, group_id in list(self.data.get("groups", {}).items()):
            groups = self.aws("ec2", "describe-security-groups", "--filters", f"Name=group-id,Values={group_id}")["SecurityGroups"]
            if not groups:
                continue
            group = groups[0]
            self.expect_owner(group["Tags"])
            for key, operation in (("IpPermissions", "revoke-security-group-ingress"),
                                   ("IpPermissionsEgress", "revoke-security-group-egress")):
                if group[key]:
                    self.aws("ec2", operation, "--group-id", group_id, "--ip-permissions", json.dumps(group[key]))
        for group_id in self.data.get("groups", {}).values():
            groups = self.aws("ec2", "describe-security-groups", "--filters", f"Name=group-id,Values={group_id}")["SecurityGroups"]
            if groups:
                self.expect_owner(groups[0]["Tags"])
                self.aws("ec2", "delete-security-group", "--group-id", group_id)
        if self.data.get("key_name"):
            keys = self.aws("ec2", "describe-key-pairs", "--filters", f"Name=key-name,Values={self.data['key_name']}")["KeyPairs"]
            if keys:
                self.expect_owner(keys[0]["Tags"])
                self.aws("ec2", "delete-key-pair", "--key-name", self.data["key_name"])
        owned_volumes = self.aws("ec2", "describe-volumes", "--filters",
                                 f"Name=tag:campaign_owner,Values={self.data['owner']}")["Volumes"]
        owned_groups = self.aws("ec2", "describe-security-groups", "--filters",
                                f"Name=tag:campaign_owner,Values={self.data['owner']}")["SecurityGroups"]
        owned_keys = self.aws("ec2", "describe-key-pairs", "--filters",
                              f"Name=tag:campaign_owner,Values={self.data['owner']}")["KeyPairs"]
        assert owned_volumes == [], owned_volumes
        assert owned_groups == [], owned_groups
        assert owned_keys == [], owned_keys
        self.data["cleanup"] = {"at": now(), "instances": self.data.get("instances", {}),
                                "volumes": owned_volumes, "groups": owned_groups, "keys": owned_keys}
        self.phase("terminated")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    parser.add_argument("--profile", default="eurosafeai")
    commands = parser.add_subparsers(dest="action", required=True)
    create = commands.add_parser("create")
    create.add_argument("--trial", required=True)
    create.add_argument("--ami")
    base = commands.add_parser("base")
    base.add_argument("--pi-version", default="0.73.1")
    base.add_argument("--multica-version", default="0.6.1")
    base.add_argument("--node-package-version", default="")
    for name in ("lockdown", "verify", "teardown", "show"):
        commands.add_parser(name)
    ssh = commands.add_parser("ssh")
    ssh.add_argument("--role", choices=ROLES, required=True)
    ssh.add_argument("command", nargs=argparse.REMAINDER)
    copy = commands.add_parser("copy")
    copy.add_argument("--role", choices=ROLES, required=True)
    copy.add_argument("--source", required=True)
    copy.add_argument("--destination", required=True)
    args = parser.parse_args()
    trial = Trial(args.state, args.profile)
    if args.action == "create":
        trial.create(args.trial, args.ami)
    elif args.action == "base":
        trial.base(args.pi_version, args.multica_version, args.node_package_version)
    elif args.action == "ssh":
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        assert command
        trial.ssh(args.role, command[0] if len(command) == 1 else shlex.join(command))
    elif args.action == "copy":
        trial.copy(args.role, args.source, args.destination)
    elif args.action == "show":
        print(json.dumps(trial.data, indent=2))
    else:
        getattr(trial, args.action)()


if __name__ == "__main__":
    main()
