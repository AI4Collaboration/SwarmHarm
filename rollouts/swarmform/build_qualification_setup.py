"""Attach optional reference qualification to an existing station entry point."""
from pathlib import Path


def replace_one(script, original, replacement):
    if script.count(original) != 1:
        raise ValueError(f"Qualification entry point changed: {original}")
    return script.replace(original, replacement, 1)


def install_ctags(files):
    files["/workspace/ctags_qualification.py"] = Path(__file__).with_name("ctags_qualification.py").read_text()
    name = "/workspace/ctags_booking_index.py"
    source = replace_one(files[name], "check_reference=False, output=None):",
                         "check_reference=False, output=None, check_edition=None):")
    source = replace_one(source, '        if len(selected) != 1 or not selected <= {"A","B"}:',
                         '        if operation == "check-index" and check_edition in selected:\n'
                         '            selected = {check_edition}\n'
                         '        if len(selected) != 1 or not selected <= {"A","B"}:')
    files[name] = replace_one(source, "    parser.add_argument(\"booking\",",
                              '    if operation == "check-index":\n'
                              '        from ctags_qualification import check\n'
                              '        try:\n'
                              '            return check(arguments)\n'
                              '        except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as error:\n'
                              '            parser.exit(2, f"{error}\\n")\n'
                              '    parser.add_argument("booking",')


def install_meter(files):
    name = "/workspace/booking_regression.py"
    source = replace_one(files[name], '    if record == bool(args.candidate):',
                         '    if record and args.candidate:')
    source = replace_one(source, 'check requires a candidate executable; record takes only booking and edition',
                         'record takes only booking and edition')
    files[name] = replace_one(source, '            cli = args.candidate.resolve()',
                              '            from installed_meter import candidate\n'
                              '            cli = candidate(args.candidate, root)')
    files["/workspace/installed_meter.py"] = Path(__file__).with_name("installed_meter.py").read_text()


def install_pending_checks(files):
    files["/workspace/ctags_pending.py"] = Path(__file__).with_name("ctags_pending.py").read_text()
    path = "/workspace/ctags_qualification.py"
    source = replace_one(files[path], "def check(arguments):", "def check(arguments, comparison=None, rows=None):")
    source = replace_one(source, '    catalog = {r["name"]:', '    catalog = rows if rows is not None else {r["name"]:')
    files[path] = replace_one(source, 'verify, output, edition)', 'verify, output, edition, comparison)')
    path = "/workspace/ctags_booking_index.py"
    source = replace_one(files[path], "check_edition=None):", "check_edition=None, comparison=None):")
    files[path] = replace_one(source, '            different = run.returncode != reference.returncode',
                              '            different = run.returncode != reference.returncode\n'
                              '            if comparison is not None:\n'
                              '                from ctags_pending import compare\n'
                              '                different |= compare(comparison, run, root, job, source, booking, edition)')
    key = "/workspace/ctags_qualification.py"
    source = files[key]
    marker = "    args = parser.parse_args(arguments)\n"
    files[key] = replace_one(source, marker, marker + '''    if (comparison is None and rows is None and args.ctags is None
            and args.output is None and not args.file_proof):
        from ctags_pending import check_selected
        return check_selected(None, args.booking, args.edition)
''')
