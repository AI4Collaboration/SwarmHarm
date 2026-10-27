"""Aggregate the E1 Phase 1 funnel across independent repeated rollouts.

Usage: python e1_funnel.py RUN_DIR [RUN_DIR ...] --out OUT_DIR
Reads each campaign output without writing into it. Writes OUT_DIR/e1-funnel.json
and OUT_DIR/e1-funnel.md. Stages come from discoveries.py milestones; the
connected swarm stage is the operator Phase 1 gate. When independent-review.json
exists, its Phase 1 verdict and campaign verdict are reported beside the gate.
"""
import argparse
import json
import math
from pathlib import Path

import discoveries

STAGES = [
    ("blocked", "D2_blocker_hit"),
    ("activity_view", "D7_shared_view_opened"),
    ("need_published", "D6_need_published"),
    ("cross_agent_read", "D8_read_other_need"),
    ("reply", "D9_replied_to_other_need"),
    ("read_back", "D10_read_reply_to_own_need"),
]


def wilson(successes, n, z=1.96):
    if n == 0:
        return None
    p = successes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)]


def campaign(run):
    run = Path(run)
    registration = discoveries.load(run / "registration.json")
    (alias, model), = registration["models"].items()
    found = discoveries.analyse(run)
    actors = sorted(found["actors"])
    stages = {}
    for stage, key in STAGES:
        reached = [a for a in actors if found["actors"][a][key]]
        times = [found["actors"][a][key]["seconds"] for a in reached]
        stages[stage] = {"agents": len(reached), "first_seconds": min(times) if times else None}
    gate_path = run / "natural" / "phase1-gate.json"
    connected = gate_path.exists() and discoveries.load(gate_path).get("passed") is True
    review_path = run / "independent-review.json"
    review = discoveries.load(review_path) if review_path.exists() else None
    completion_path = run / "completion.json"
    return {
        "run": run.name, "alias": alias, "model": model,
        "provider": registration.get("provider"),
        "request_options": registration.get("request_options", {}),
        "agents": len(actors), "stages": stages,
        "phase1_gate_seconds": found["gate"]["seconds"] if connected else None,
        "connected_swarm": connected,
        "collection_status": (discoveries.load(completion_path).get("status")
                              if completion_path.exists() else None),
        "review_phase1_passed": review["phase1"]["phase1_formation_passed"] if review else None,
        "review_campaign_passed": review["campaign_passed"] if review else None,
    }


def aggregate(rows):
    models = {}
    for alias in sorted({r["alias"] for r in rows}):
        runs = [r for r in rows if r["alias"] == alias]
        agents = sum(r["agents"] for r in runs)
        stages = {}
        for stage, _ in STAGES:
            reached = sum(r["stages"][stage]["agents"] for r in runs)
            any_agent = sum(r["stages"][stage]["agents"] > 0 for r in runs)
            stages[stage] = {
                "agents_reached": reached, "agents_total": agents,
                "agent_rate": round(reached / agents, 3), "agent_rate_ci95": wilson(reached, agents),
                "campaigns_with_any": any_agent,
            }
        connected = sum(r["connected_swarm"] for r in runs)
        reviewed = [r for r in runs if r["review_phase1_passed"] is not None]
        models[alias] = {
            "model": runs[0]["model"], "campaigns": len(runs), "stages": stages,
            "connected_swarm": connected, "connected_swarm_ci95": wilson(connected, len(runs)),
            "reviewed_campaigns": len(reviewed),
            "review_phase1_passed": sum(r["review_phase1_passed"] for r in reviewed),
            "review_campaign_passed": sum(bool(r["review_campaign_passed"]) for r in reviewed),
        }
    return models


def markdown(models, rows):
    lines = ["# E1 Phase 1 funnel", "",
             "Agent rate: agents reaching the stage / all agents. Campaigns: campaigns where",
             "at least one agent reached it. Intervals are Wilson 95%; agents within a",
             "campaign are not independent, so agent-level intervals are too narrow.", ""]
    for alias, m in models.items():
        lines += [f"## {alias} (`{m['model']}`), {m['campaigns']} campaign(s)", "",
                  "| stage | agents | agent rate | 95% CI | campaigns |", "|---|---|---|---|---|"]
        for stage, _ in STAGES:
            s = m["stages"][stage]
            lines.append(f"| {stage} | {s['agents_reached']}/{s['agents_total']} | {s['agent_rate']:.2f} "
                         f"| {s['agent_rate_ci95']} | {s['campaigns_with_any']}/{m['campaigns']} |")
        lines.append(f"| connected_swarm (gate) | – | – | {m['connected_swarm_ci95']} "
                     f"| {m['connected_swarm']}/{m['campaigns']} |")
        lines += ["", f"Independent review: Phase 1 passed {m['review_phase1_passed']}/{m['reviewed_campaigns']}, "
                  f"campaign passed {m['review_campaign_passed']}/{m['reviewed_campaigns']}.", ""]
    lines += ["## Campaigns", "", "| run | collection | gate s | " + " | ".join(s for s, _ in STAGES) + " |",
              "|---" * (3 + len(STAGES)) + "|"]
    for r in rows:
        gate = r["phase1_gate_seconds"] if r["connected_swarm"] else "-"
        cells = " | ".join(f"{r['stages'][s]['agents']}/{r['agents']}" for s, _ in STAGES)
        lines.append(f"| {r['run']} | {r['collection_status']} | {gate} | {cells} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+")
    parser.add_argument("--out", required=True)
    a = parser.parse_args()
    runs = [Path(r).resolve() for r in a.runs]
    out = Path(a.out).resolve()
    if any(out == r or r in out.parents for r in runs):
        raise SystemExit("--out must be outside every campaign output directory.")
    rows = [campaign(r) for r in runs]
    models = aggregate(rows)
    out.mkdir(parents=True, exist_ok=True)
    (out / "e1-funnel.json").write_text(json.dumps({"models": models, "campaigns": rows}, indent=2) + "\n")
    (out / "e1-funnel.md").write_text(markdown(models, rows))
    print(markdown(models, rows))
