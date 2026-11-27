"""Render the field guide or one booking's commissioning entry."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

from guide_full import ExternalLinks, main as full_guide
from published_inputs import published_inputs

MEMBERS = {"north": "BridgeConverter::force", "crossing": "ShaftCounter::rpm", "harbor": "LimitLatch::update"}


def entry(booking):
    guide = Path(__file__).with_name("field-guide")
    config = (guide / "Doxyfile").read_text()
    document = (guide / "commissioning.dox").read_text()
    member = MEMBERS[booking]
    reference = re.search(r'\\ref\s+' + re.escape(member) + r'\s+"[^"]+"', document)
    if not reference:
        sys.exit(f"Guide entry missing: {member}")
    name = f"manual/{booking}.tag"
    setting = re.search(r"(?m)^TAGFILES\s*=\s*(.+)$", config)
    target = next(x for x in setting[1].split() if x.partition("=")[0] == name)
    try:
        with published_inputs([name], {}) as root:
            local = root / "field-guide"
            local.mkdir()
            (local / "Doxyfile").write_text(config[:setting.start(1)] + target + config[setting.end(1):])
            (local / "commissioning.dox").write_text("/*! \\mainpage Commissioning\n" + reference[0] + "\n*/\n")
            subprocess.run(["/opt/programbench/invoke", "doxygen__doxygen.966d98e", "field-guide/Doxyfile"],
                           cwd=root, check=True, stdout=sys.stderr)
            links = ExternalLinks()
            links.feed((root / "build/html/index.html").read_text())
    except (KeyError, FileNotFoundError) as error:
        sys.exit(f"Field guide input unavailable: {error}")
    href = links.links.get(member, "")
    if not href.partition("#")[2]:
        sys.exit(f"Field guide reference unresolved: {member}")
    print(json.dumps({member: href}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("booking", choices=MEMBERS, nargs="?")
    selected = parser.parse_args().booking
    entry(selected) if selected else full_guide()
