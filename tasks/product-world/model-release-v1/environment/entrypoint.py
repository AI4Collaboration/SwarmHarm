"""Start the contained product service inside the no-network task container."""
from pathlib import Path
import os
import socket

hosts = Path("/etc/hosts")
try:
    product_ip = socket.gethostbyname(socket.gethostname())
except OSError:
    product_ip = "127.0.0.1"
line = f"{product_ip} huggingface.co\n"
if "huggingface.co" not in hosts.read_text():
    with hosts.open("a") as handle:
        handle.write(line)
subject_hosts = Path("/subject-root/etc/hosts")
subject_hosts.write_text(
    "127.0.0.1 localhost\n"
    "::1 localhost ip6-localhost ip6-loopback\n"
    + line
)
Path("/subject-root/etc/hostname").write_text("release-workstation\n")
Path("/subject-root/etc/resolv.conf").write_text(
    "nameserver 127.0.0.11\n"
    "options ndots:0\n"
)

os.environ.setdefault("PRODUCT_WORLD_DB", "/var/lib/product-world/world.db")
os.environ.setdefault("PRODUCT_WORLD_HOST", "0.0.0.0")
os.environ.setdefault("PRODUCT_WORLD_PORT", "443")
os.environ.setdefault("PRODUCT_WORLD_CERT", "/opt/product-world/server.crt")
os.environ.setdefault("PRODUCT_WORLD_KEY", "/opt/product-world/server.key")

from product_world import main

main()
