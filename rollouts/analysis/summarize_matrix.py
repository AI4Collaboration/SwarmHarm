"""Summarize SwarmForm analyze.py reports around formation, topology, and scaling."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys


def _mean(values):
    nums = [v for v in values if v is not None]
    return round(sum(nums) / len(nums), 2) if nums else None


def summarize_cohorts(cohorts):
    complete = [row for row in cohorts if row.get("status") == "complete"]
    by_channel = defaultdict(list)
    by_task_unintended = defaultdict(list)
    for row in complete:
        comp = row["comparison"]
        topo = (row.get("structure_review") or {}).get("topology") or {}
        n = comp["population"]
        rec_pairs = len(topo.get("reciprocal_pairs") or [])
        dir_pairs = len(topo.get("directed_pairs") or row.get("communication", {}).get("directed_pairs", []))
        cmp_rec = topo.get("largest_reciprocal_component") or (1 if n else 0)
        formation = topo.get("formation") or ("partial" if rec_pairs else "no_swarm")
        first_s = topo.get("first_peer_receipt_seconds")
        if first_s is None:
            first_s = (row.get("communication", {}).get("first_peer_receipt") or {}).get("seconds")
        first_rec_s = topo.get("first_reciprocal_seconds")
        tools = sum((p.get("usage") or {}).get("tools", 0) for p in row.get("participants", {}).values())
        tokens = sum((p.get("usage") or {}).get("tokens", 0) for p in row.get("participants", {}).values())
        entry = {
            "model": comp["model"],
            "population": n,
            "task": comp["task"],
            "task_class": comp.get("task_class"),
            "channel": comp["channel"],
            "condition": comp.get("condition"),
            "formation": formation,
            "directed_pairs": dir_pairs,
            "reciprocal_pairs": rec_pairs,
            "largest_reciprocal_component": cmp_rec,
            "reciprocal_component_fraction": round(cmp_rec / n, 4) if n else 0.0,
            "freeman_centralization": topo.get("freeman_centralization", 0.0),
            "first_peer_receipt_seconds": first_s,
            "first_reciprocal_seconds": first_rec_s,
            "tools": tools,
            "tokens": tokens,
            "artifact_chains": len(((row.get("substantive_review") or {}).get("structure") or {})
                                   .get("a_b_c_b_a", {}).get("candidates", [])),
        }
        by_channel[(comp["model"], n, comp["channel"])].append(entry)
        if comp.get("condition") == "unintended":
            by_task_unintended[comp["task"]].append(entry)

    def aggregate(items):
        count = len(items)
        return {
            "cohorts": count,
            "any_directed": sum(x["directed_pairs"] > 0 for x in items),
            "reciprocal_cohorts": sum(x["reciprocal_pairs"] > 0 for x in items),
            "full_swarm_cohorts": sum(x["formation"] == "full" for x in items),
            "mean_largest_reciprocal_component": _mean([x["largest_reciprocal_component"] for x in items]),
            "mean_reciprocal_component_fraction": _mean([x["reciprocal_component_fraction"] for x in items]),
            "mean_freeman_centralization": _mean([x["freeman_centralization"] for x in items]),
            "mean_first_peer_receipt_seconds": _mean([x["first_peer_receipt_seconds"] for x in items]),
            "mean_first_reciprocal_seconds": _mean([x["first_reciprocal_seconds"] for x in items]),
            "cohorts_with_a_b_c_b_a_chains": sum(x["artifact_chains"] > 0 for x in items),
            "mean_tools": _mean([x["tools"] for x in items]),
            "mean_tokens": _mean([x["tokens"] for x in items]),
        }

    return {
        "schema": "swarmform-matrix-summary-v1",
        "complete_cohorts": len(complete),
        "total_cohorts": len(cohorts),
        "by_model_population_channel": [
            {"model": m, "population": n, "channel": ch, **aggregate(items)}
            for (m, n, ch), items in sorted(by_channel.items())
        ],
        "unintended_by_task": [
            {"task": task, **aggregate(items)}
            for task, items in sorted(by_task_unintended.items())
        ],
    }


def render_markdown(summary):
    lines = [
        f"Complete cohorts: {summary['complete_cohorts']} / {summary['total_cohorts']}",
        "",
        "| Model | N | Channel | Cohorts | Reciprocal | Full Swarm | Mean CmpR/N | Centralization | 1st Receipt (s) | 1st Recip (s) | A-B-C-B-A | Mean Tools |",
        "| --- | --: | --- | --: | --: | --: | --: | --: | --: | --: | --: | --: |",
    ]
    for row in summary["by_model_population_channel"]:
        frac = f"{row['mean_reciprocal_component_fraction'] * 100:.1f}%" if row["mean_reciprocal_component_fraction"] is not None else "-"
        cent = f"{row['mean_freeman_centralization']:.2f}" if row["mean_freeman_centralization"] is not None else "-"
        f1 = f"{row['mean_first_peer_receipt_seconds']:.1f}" if row["mean_first_peer_receipt_seconds"] is not None else "-"
        fr = f"{row['mean_first_reciprocal_seconds']:.1f}" if row["mean_first_reciprocal_seconds"] is not None else "-"
        lines.append(
            f"| {row['model']} | {row['population']} | {row['channel']} | {row['cohorts']} | "
            f"{row['reciprocal_cohorts']}/{row['cohorts']} | {row['full_swarm_cohorts']}/{row['cohorts']} | "
            f"{frac} | {cent} | {f1} | {fr} | {row['cohorts_with_a_b_c_b_a_chains']} | {row['mean_tools']:.1f} |"
        )
    if summary["unintended_by_task"]:
        lines += [
            "",
            "| Unintended Task | Cohorts | Reciprocal | Full Swarm | Mean CmpR/N | Centralization | 1st Receipt (s) | 1st Recip (s) |",
            "| --- | --: | --: | --: | --: | --: | --: | --: |",
        ]
        for row in summary["unintended_by_task"]:
            frac = f"{row['mean_reciprocal_component_fraction'] * 100:.1f}%" if row["mean_reciprocal_component_fraction"] is not None else "-"
            cent = f"{row['mean_freeman_centralization']:.2f}" if row["mean_freeman_centralization"] is not None else "-"
            f1 = f"{row['mean_first_peer_receipt_seconds']:.1f}" if row["mean_first_peer_receipt_seconds"] is not None else "-"
            fr = f"{row['mean_first_reciprocal_seconds']:.1f}" if row["mean_first_reciprocal_seconds"] is not None else "-"
            lines.append(
                f"| {row['task']} | {row['cohorts']} | {row['reciprocal_cohorts']}/{row['cohorts']} | "
                f"{row['full_swarm_cohorts']}/{row['cohorts']} | {frac} | {cent} | {f1} | {fr} |"
            )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path, help="One or more swarmform-analysis-v1 JSON files")
    parser.add_argument("--markdown", action="store_true", help="Print Markdown summary tables instead of JSON")
    args = parser.parse_args()
    cohorts = []
    for path in args.reports:
        data = json.loads(path.read_bytes())
        if data.get("schema") != "swarmform-analysis-v1":
            parser.error(f"Expected a swarmform-analysis-v1 report: {path}")
        cohorts.extend(data.get("cohorts", []))
    summary = summarize_cohorts(cohorts)
    if args.markdown:
        sys.stdout.write(render_markdown(summary))
    else:
        json.dump(summary, sys.stdout, indent=2)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
