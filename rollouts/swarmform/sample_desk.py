"""Open a calibration booking or register one of its issued orders."""
import argparse
import json
from pathlib import Path
import shutil

from calibration_cases import PREFIX, filed_records, project


def checkout(booking, records, root):
    files = {}
    for receipt in records:
        name, body = receipt["name"], receipt["text"]
        if name.startswith(PREFIX):
            case = json.loads(body)
            for sample in case.get("samples", []):
                if sample["booking"] != booking or sample["edition"] not in {"A", "B"} or sample["file"] != "argon.gro":
                    continue
                key = f"bookings/{booking}/{sample['edition']}/argon.gro"
                source = case["files"][sample["file"]]
                if key in files and files[key] != source:
                    raise ValueError(f"Filed measurements disagree on the source for {key}")
                files[key] = source
        elif name.startswith("calibration/orders/"):
            basename = Path(name).name
            if basename not in {booking+".json", booking+"-release.json"}:
                raise ValueError(f"Unrecognized filed order: {name}")
            files["orders/"+basename] = body
        elif name == "structures/"+booking+".gro":
            files[name] = body
    root.mkdir()
    try:
        for name, body in files.items():
            path = root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body.encode())
    except Exception:
        shutil.rmtree(root)
        raise
    print(json.dumps({"booking":booking, "directory":str(root), "files":sorted(files)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("booking", choices=("north", "crossing", "harbor"))
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--order", type=Path, help="File a local release-order copy")
    action.add_argument("--checkout", type=Path, help="Open a fresh booking directory from filed samples, orders and any issued product")
    action.add_argument("--product", type=Path, help="Issue the selected centered lattice at this booking")
    parser.add_argument("--if-version", type=int, default=0)
    args = parser.parse_args()
    order_prefix = "calibration/orders/" + args.booking + "/"
    product = "structures/" + args.booking + ".gro"
    if args.product is not None:
        print(json.dumps(project("write", product, str(args.product), "--if-version", str(args.if_version))))
        return
    if args.order:
        path = args.order.resolve(strict=True)
        if path.parent != Path("/workspace/orders") or path.suffix != ".json":
            parser.error("Select a release order from /workspace/orders")
        order = json.loads(path.read_bytes())
        if order.get("booking") != args.booking or order.get("status") != "in force":
            parser.error("The order does not apply to this booking")
        print(json.dumps(project("write", order_prefix + path.name, str(path),
                                 "--if-version", str(args.if_version))))
        return
    if args.if_version:
        parser.error("--if-version applies when filing an order or issuing a product")
    records = []
    for receipt in filed_records(lambda name: name == product or name.startswith((order_prefix, PREFIX))):
        name = receipt["name"]
        if name.startswith(PREFIX):
            case = json.loads(receipt["text"])
            if not any(sample["booking"] == args.booking for sample in case.get("samples", [])):
                continue
        records.append(receipt)
    if args.checkout is not None:
        checkout(args.booking, records, args.checkout)
    else:
        print(json.dumps({"booking": args.booking, "records": records}, ensure_ascii=False))


if __name__ == "__main__":
    main()
