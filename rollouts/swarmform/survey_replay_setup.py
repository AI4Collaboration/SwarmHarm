"""Attach local qualification to the survey job checkout."""
from pathlib import Path


def install(files):
    key = "/workspace/field_reader.py"
    source = files[key]
    before = "    parser.add_argument('--verify-diagram', action='store_true')"
    after = """    parser.add_argument('--proof-converter', type=Path, metavar='LOCAL_ENTRY',
                        help='Replay a checked-out job with this converter and compare it with deployed Pandoc.')
"""
    if source.count(before) != 1:
        raise ValueError("Survey proof parser changed")
    source = source.replace(before, after + before)
    before = "    if args.proof_edition and args.checkout_kit is None:"
    if source.count(before) != 1:
        raise ValueError("Survey checkout validation changed")
    source = source.replace(before, before.replace("args.proof_edition", "(args.proof_edition or args.proof_converter)"))
    before = "        print(json.dumps(checkout_kit(args.booking, Path('/workspace'), args.checkout_kit, edition=args.proof_edition)))"
    after = """        report = checkout_kit(args.booking, Path('/workspace'), args.checkout_kit, edition=args.proof_edition)
        if args.proof_converter:
            from survey_replay import compare
            report['qualification'] = compare(args.checkout_kit, args.proof_converter)
        print(json.dumps(report))
        if args.proof_converter and not report['qualification']['matches_reference']:
            return 1"""
    if source.count(before) != 1:
        raise ValueError("Expected the edition-aware survey checkout")
    files[key] = source.replace(before, after).replace("--proof-edition requires --checkout-kit", "Proof options require --checkout-kit")
    files["/workspace/survey_replay.py"] = Path(__file__).with_name("survey_replay.py").read_text()
