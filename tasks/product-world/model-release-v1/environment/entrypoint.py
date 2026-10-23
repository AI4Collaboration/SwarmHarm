"""Start the contained product service inside the no-network task container."""
from pathlib import Path
import os

hosts = Path("/etc/hosts")
line = "127.0.0.1 huggingface.co\n"
if "huggingface.co" not in hosts.read_text():
    with hosts.open("a") as handle:
        handle.write(line)

os.environ.setdefault("PRODUCT_WORLD_DB", "/var/lib/product-world/world.db")
os.environ.setdefault("PRODUCT_WORLD_HOST", "0.0.0.0")
os.environ.setdefault("PRODUCT_WORLD_PORT", "443")
os.environ.setdefault("PRODUCT_WORLD_CERT", "/opt/product-world/server.crt")
os.environ.setdefault("PRODUCT_WORLD_KEY", "/opt/product-world/server.key")

from product_world import main

main()
