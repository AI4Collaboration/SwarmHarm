"""Render the issued field guide against its published interface tags."""
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import sys

from published_inputs import published_inputs


class ExternalLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and "elRef" in attrs.get("class", "").split():
            self.links[attrs.get("title", "")] = attrs.get("href", "")


def main():
    guide = Path(__file__).with_name("field-guide")
    config = (guide / "Doxyfile").read_text()
    document = (guide / "commissioning.dox").read_text()
    targets = re.search(r"(?m)^TAGFILES\s*=\s*(.+)$", config).group(1).split()
    names = [target.split("=", 1)[0] for target in targets]
    try:
        with published_inputs(names, {}) as root:
            local_guide = root / "field-guide"
            local_guide.mkdir()
            (local_guide / "Doxyfile").write_text(config)
            (local_guide / "commissioning.dox").write_text(document)
            subprocess.run(["/opt/programbench/invoke", "doxygen__doxygen.966d98e",
                            "field-guide/Doxyfile"], cwd=root, check=True, stdout=sys.stderr)
            links = ExternalLinks()
            links.feed((root / "build/html/index.html").read_text())
    except (FileNotFoundError, KeyError) as error:
        sys.exit(f"Field guide input unavailable: {error}")
    symbols = re.findall(r'\\ref\s+(\S+)\s+"[^"]+"', document)
    for symbol in symbols:
        href = links.links.get(symbol, "")
        if not href.partition("#")[2]:
            sys.exit(f"Field guide reference unresolved: {symbol}")
    print(json.dumps({symbol: links.links[symbol] for symbol in symbols}))


if __name__ == "__main__":
    main()
