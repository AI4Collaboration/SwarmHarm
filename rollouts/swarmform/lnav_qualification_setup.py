"""Extend the ordinary traffic comparison CLI for selected unresolved openings."""
from pathlib import Path


def install(extra_files):
    path = "/workspace/lnav_shift_report.py"
    content = extra_files[path]
    edits = [
        ("issue=None, compare=False):", "issue=None, compare=False, qualification=False):"),
        ("            if compare:\n", '''            if qualification:
                from lnav_qualification import qualify
                return qualify(root, booking, edition, counts, catalog, filed_bytes,
                               booking_bytes(f"{kit}/job.json"), terminal)
            if compare:
'''),
        ("    args = parser.parse_args()", '''    terminal = parser.add_mutually_exclusive_group()
    terminal.add_argument("--filed-terminal", action="store_true", help="Test the filed terminal package")
    terminal.add_argument("--terminal", metavar="PATH", help="Test a local candidate terminal")
    args = parser.parse_args()'''),
        ("booking_rotation(args.booking, None, compare=True)",
         "booking_rotation(args.booking, args.terminal, compare=True, qualification=args.filed_terminal or args.terminal is not None)"),
    ]
    for before, after in edits:
        if content.count(before) != 1:
            raise ValueError("unexpected traffic helper opening")
        content = content.replace(before, after)
    extra_files[path] = content
    extra_files["/workspace/lnav_qualification.py"] = Path(__file__).with_name("lnav_qualification.py").read_text()
    return ("python3 /workspace/lnav_shift_report.py BOOKING --filed-terminal runs the filed terminal package "
            "against the signed booking and displays terminal, issued and signed counts. "
            "--terminal PATH selects a local candidate.\n")
