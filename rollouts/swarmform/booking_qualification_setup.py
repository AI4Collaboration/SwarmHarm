"""Add edition-specific local qualification to an assembled station tool."""


def replace_one(source, old, new):
    if source.count(old) != 1:
        raise ValueError("Expected exactly one qualification insertion point")
    return source.replace(old, new, 1)


def install(files, family):
    if family == "pandoc":
        path = "/workspace/field_reader.py"
        source = files[path]
        source = replace_one(source,
            'def checkout_kit(booking, workspace, directory, catalog=None):\n    catalog = catalog_versions(workspace) if catalog is None else catalog\n    kit = issued_kit(booking, workspace, catalog)\n',
            'def checkout_kit(booking, workspace, directory, catalog=None, edition=None):\n    catalog = catalog_versions(workspace) if catalog is None else catalog\n    kit = (workspace / "bookings" / booking / edition if edition is not None\n           else issued_kit(booking, workspace, catalog))\n')
        source = replace_one(source,
            "                        help='Open the signed survey source, recorded job and issued plate in a new local directory.')\n",
            "                        help='Open the signed survey source, recorded job and issued plate in a new local directory.')\n    parser.add_argument('--proof-edition', choices=('A', 'B'),\n                        help='Select an edition for a local proof checkout.')\n")
        source = replace_one(source,
            '    args = parser.parse_args()\n',
            "    args = parser.parse_args()\n    if args.proof_edition and args.checkout_kit is None:\n        parser.error('--proof-edition requires --checkout-kit')\n")
        source = replace_one(source,
            "        print(json.dumps(checkout_kit(args.booking, Path('/workspace'), args.checkout_kit)))\n",
            "        print(json.dumps(checkout_kit(args.booking, Path('/workspace'), args.checkout_kit, edition=args.proof_edition)))\n")
    elif family == "duckdb":
        path = "/workspace/weighbridge.py"
        source = files[path]
        source = replace_one(source,
            '    if not args.booking or args.version is not None or ((args.check_ledger or args.working) and args.if_version is not None):\n',
            '    working = bool(args.working or args.save_working or args.check_working)\n    if not args.booking or args.version is not None or ((args.check_ledger or args.working or args.check_working) and args.if_version is not None):\n')
        source = replace_one(source,
            '                orders.append(order["approved_edition"])\n    if args.working or args.save_working:\n',
            '                orders.append(order["approved_edition"])\n    if working:\n')
        source = replace_one(source,
            '    terminal = args.check_ledger or args.issue_ledger\n',
            '    terminal = args.check_working or args.check_ledger or args.issue_ledger\n')
        source = replace_one(source,
            '        if args.working or args.save_working:\n',
            '        if working:\n')
        source = replace_one(source,
            '    actions.add_argument("--issue-ledger", type=Path, metavar="TERMINAL", help="Issue the signed ledger after the selected terminal agrees with stock DuckDB")\n',
            '    actions.add_argument("--issue-ledger", type=Path, metavar="TERMINAL", help="Issue the signed ledger after the selected terminal agrees with stock DuckDB")\n    actions.add_argument("--check-working", type=Path, metavar="TERMINAL", help="Compare a selected edition on a local terminal with the deployed terminal")\n')
        source = replace_one(source,
            '    if args.check_ledger or args.issue_ledger or args.working or args.save_working:\n',
            '    if args.check_ledger or args.issue_ledger or args.working or args.save_working or args.check_working:\n')
    else:
        raise ValueError(f"Unsupported qualification family: {family}")
    files[path] = source
