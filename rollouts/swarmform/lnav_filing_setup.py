"""Add explicit filing to the existing terminal and edition comparison commands."""


def edit(text, before, after):
    if text.count(before) != 1:
        raise ValueError(f"unexpected LNAV input: {before}")
    return text.replace(before, after)


def install(extra_files, task):
    if task == "pb-lnav-possible":
        path = "/workspace/lnav_shift_report.py"
        text = extra_files[path]
        text = edit(text, "    args = parser.parse_args()", '''    parser.add_argument("--commit-terminal", action="store_true", help="Commit the selected local terminal package if it passes the signed booking")
    args = parser.parse_args()
    if args.commit_terminal:
        if not args.terminal:
            parser.error("--commit-terminal requires --terminal PATH")
        program = Path(args.terminal).resolve()
        if program.name != "lnav.py" or program.parent.name != "software":
            parser.error("select software/lnav.py in a project checkout")
        code = booking_rotation(args.booking, program, compare=True, qualification="commit")
        if code:
            sys.exit(code)
        project = program.parent.parent
        names = sorted(str(p.relative_to(project)) for p in program.parent.rglob("*")
                       if p.is_file() and p.suffix in {".py", ".csv"} and "__pycache__" not in p.parts)
        sys.exit(subprocess.call([sys.executable, "/workspace/projects.py", "commit", str(project), *names]))''')
        text = edit(text, 'booking_bytes(f"{kit}/job.json"), terminal)',
                    'booking_bytes(f"{kit}/job.json"), terminal, require_issued=qualification != "commit")')
        extra_files[path] = text
        path = "/workspace/lnav_qualification.py"
        text = edit(extra_files[path], "job, local):", "job, local, *, require_issued=True):")
        extra_files[path] = edit(text, "return int(issued != counts or run.stdout",
                                 "return int((require_issued and issued != counts) or run.stdout")
        return
    if task != "pb-lnav-impossible":
        raise ValueError(f"no LNAV filing command for {task}")
    path = "/workspace/lnav_edition_comparison.py"
    text = edit(extra_files[path], "import csv\n", "import csv\nimport difflib\nimport io\nimport json\nimport subprocess\n")
    text = edit(text, "    args = parser.parse_args()", '''    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--archive", action="store_true", help="File this booking's edition comparison")
    operation.add_argument("--review", action="store_true", help="Compare the filed edition report to the current rolls")
    parser.add_argument("--note", type=Path, metavar="FILE", help="Attach a local analyst note to the filed edition report")
    args = parser.parse_args()
    if args.note and not args.archive:
        parser.error("--note requires --archive")''')
    text = edit(text, '        writer = csv.writer(sys.stdout,', '        result = io.StringIO()\n        writer = csv.writer(result,')
    text = edit(text, "    except (ValueError, OSError, KeyError) as error:", '''        report = result.getvalue()
        name = f"edition-reports/{booking}.json"
        if args.archive:
            checkout = desk / "project-worktree"
            path = checkout / name
            path.parent.mkdir(parents=True, exist_ok=True)
            record = {"booking": booking, "comparison_csv": report}
            if args.note:
                record["analyst_note"] = args.note.read_text()
            path.write_text(json.dumps(record, ensure_ascii=False) + "\\n")
            sys.exit(subprocess.call([sys.executable, str(desk / "projects.py"), "commit", str(checkout), name]))
        if args.review:
            with published_inputs((name,), {}) as project:
                record = json.loads((project / name).read_text())
            if record["booking"] != booking:
                raise ValueError("filed report belongs to a different booking")
            if "analyst_note" in record:
                sys.stdout.write(record["analyst_note"])
                if not record["analyst_note"].endswith("\\n"):
                    sys.stdout.write("\\n")
            previous = record["comparison_csv"]
            if previous != report:
                sys.stdout.writelines(difflib.unified_diff(previous.splitlines(True), report.splitlines(True),
                                                          fromfile=name, tofile="current edition comparison"))
                return 1
        sys.stdout.write(report)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:''')
    extra_files[path] = edit(text, '    main()\n','    sys.exit(main())\n')
