import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess

from jinja2 import Environment, FileSystemLoader, StrictUndefined


def run(*args):
    subprocess.run(args, check=True)


def install(address, directory):
    os.environ["DEBIAN_FRONTEND"] = "noninteractive"
    scratch = Path("/opt/swh119")
    scratch.mkdir(exist_ok=True)
    (scratch / "tmp").mkdir(exist_ok=True)
    os.environ["TMPDIR"] = str(scratch / "tmp")
    run("apt-get", "update", "-q")
    run("apt-get", "install", "-y", "-q", "docker.io", "docker-compose-v2", "nginx", "ufw", "python3-venv", "curl", "jq")
    run("systemctl", "enable", "--now", "docker", "nginx")
    root = Path("/opt/multica")
    root.mkdir(exist_ok=True)
    env_path = root / ".env"
    if not env_path.exists():
        values = {
            "MULTICA_IMAGE_TAG": "v0.6.1",
            "APP_ENV": "production",
            "JWT_SECRET": secrets.token_hex(32),
            "POSTGRES_PASSWORD": secrets.token_hex(24),
            "MULTICA_VCS_SECRET_KEY": base64.b64encode(secrets.token_bytes(32)).decode(),
            "FRONTEND_ORIGIN": f"https://{address}",
            "CORS_ALLOWED_ORIGINS": f"https://{address}",
            "MULTICA_APP_URL": f"https://{address}",
            "MULTICA_PUBLIC_URL": f"https://{address}",
            "MULTICA_DAEMON_SERVER_URL": f"https://{address}",
            "MULTICA_TRUSTED_PROXIES": "127.0.0.1/32",
            "ALLOWED_EMAILS": "admin@tac.ch",
            "DO_NOT_TRACK": "1",
            "ANALYTICS_DISABLED": "true",
        }
        env_path.touch(mode=0o600)
        env_path.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
    run("curl", "-fsSL", "https://raw.githubusercontent.com/multica-ai/multica/v0.6.1/docker-compose.selfhost.yml", "-o", str(root / "docker-compose.yml"))
    templates = Environment(loader=FileSystemLoader(directory), undefined=StrictUndefined, autoescape=False)
    default = Path("/etc/nginx/sites-enabled/default")
    if default.exists():
        default.unlink()
    Path("/var/www/acme").mkdir(parents=True, exist_ok=True)
    Path("/etc/nginx/conf.d/multica-http.conf").write_text(templates.get_template("controller-http.conf.j2").render(address=address))
    run("nginx", "-t")
    run("systemctl", "reload", "nginx")
    if not Path("/opt/certbot/bin/certbot").exists():
        run("python3", "-m", "venv", "/opt/certbot")
        run("/opt/certbot/bin/pip", "install", "certbot==5.8.0")
    if not Path("/etc/letsencrypt/live/multica-ip/fullchain.pem").exists():
        run("/opt/certbot/bin/certbot", "certonly", "--webroot", "-w", "/var/www/acme", "--ip-address", address,
            "--required-profile", "shortlived", "--key-type", "ecdsa", "--cert-name", "multica-ip",
            "--non-interactive", "--agree-tos", "--no-eff-email", "-m", "swarmharm@tac.ch")
    Path("/etc/nginx/conf.d/multica-https.conf").write_text(templates.get_template("controller-https.conf.j2").render(address=address))
    run("nginx", "-t")
    run("systemctl", "reload", "nginx")
    run("docker", "compose", "--project-directory", str(root), "pull", "-q")
    run("docker", "compose", "--project-directory", str(root), "up", "-d", "--wait", "--wait-timeout", "180")
    run("ufw", "default", "deny", "incoming")
    run("ufw", "default", "allow", "outgoing")
    run("ufw", "allow", "from", "195.176.112.0/24", "to", "any", "port", "22", "proto", "tcp")
    run("ufw", "allow", "80/tcp")
    run("ufw", "allow", "443/tcp")
    run("ufw", "--force", "enable")
    run("curl", "-fsS", "--retry", "12", "--retry-delay", "1", "--retry-all-errors", "--max-time", "5", f"https://{address}/api/config")
    images = subprocess.check_output(["docker", "image", "ls", "--digests", "--format", "json"], text=True)
    (scratch / "controller-images.jsonl").write_text(images)
    print(json.dumps({"controller": address, "multica": "0.6.1", "https": "verified"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--address", required=True)
    parser.add_argument("--templates", required=True)
    args = parser.parse_args()
    install(args.address, args.templates)
