import io
import re
import sys
import tarfile
from pathlib import Path

# 对 trace 包目录内所有文件（含 .tgz 内部成员）中的凭据做替换：AxonHub key、Multica PAT、GitHub/其他 token 样式
# 用法：redact.py EXPORT_DIR；输出替换计数
PATTERNS = {
    "AXONHUB_KEY": re.compile(rb"ah-[0-9a-f]{64}"),
    "MULTICA_PAT": re.compile(rb"mul_[0-9a-f]{40}"),
    "MULTICA_AGENT_TOKEN": re.compile(rb"mat_[A-Za-z0-9_-]{20,}"),
    "SSH_PRIVATE_KEY": re.compile(rb"-----BEGIN OPENSSH PRIVATE KEY-----.*?-----END OPENSSH PRIVATE KEY-----", re.S),
}


def redact(data: bytes, counts: dict) -> bytes:
    for name, pattern in PATTERNS.items():
        data, n = pattern.subn(b"[REDACTED-" + name.encode() + b"]", data)
        if n:
            counts[name] = counts.get(name, 0) + n
    return data


def redact_tgz(path: Path, counts: dict) -> None:
    buffer = io.BytesIO()
    with tarfile.open(path, "r:gz") as src, tarfile.open(fileobj=buffer, mode="w:gz") as dst:
        for member in src.getmembers():
            if member.isfile():
                data = redact(src.extractfile(member).read(), counts)
                member.size = len(data)
                dst.addfile(member, io.BytesIO(data))
            else:
                dst.addfile(member)
    path.write_bytes(buffer.getvalue())


counts: dict = {}
for path in sorted(Path(sys.argv[1]).rglob("*")):
    if not path.is_file():
        continue
    if path.suffix in (".tgz", ".gz") and tarfile.is_tarfile(path):
        redact_tgz(path, counts)
    else:
        original = path.read_bytes()
        data = redact(original, counts)
        if data != original:
            path.write_bytes(data)
print("redacted:", counts)
