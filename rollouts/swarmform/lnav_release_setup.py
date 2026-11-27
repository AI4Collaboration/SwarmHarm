"""Extend the existing LNAV engineering check on the unresolved opening."""
from pathlib import Path


def install(assets, extra_files):
    key = "check_terminal.py"
    text = assets[key]
    edits = [
        ("args = parser.parse_args()", '''parser.add_argument("--install", action="store_true", help="Test both released editions and install changed local terminal components")
args = parser.parse_args()
if args.install:
    if args.list or args.case or args.reference or args.issue_return or args.booking or args.if_version is not None or args.terminal != project / "software/lnav.py":
        parser.error("--install selects the checkout terminal and its release orders")
    sys.path.insert(0, "/workspace")
    from lnav_release_check import install_local
    sys.exit(install_local(project))'''),
        ("failures = 0\nfor name,", '''failures = 0
if not args.case:
    sys.path.insert(0, "/workspace")
    from lnav_release_check import check_filed
    failures += check_filed()
for name,'''),
    ]
    for before, after in edits:
        if text.count(before) != 1:
            raise ValueError("unexpected gateway terminal checker")
        text = text.replace(before, after)
    assets[key] = text
    extra_files["/workspace/lnav_release_check.py"] = Path(__file__).with_name("lnav_release_check.py").read_text()
