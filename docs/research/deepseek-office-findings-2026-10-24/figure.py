"""Plot committed V3 outcomes; no model calls or raw trace access."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
summary = json.loads((ROOT / "experiments/error-propagation-v3/results/2026-10-24/summary.json").read_text())
rows = []
for snapshot in ("old", "new"):
    for arm in ("solo", "team"):
        conditions = [summary["conditions"][f"{snapshot}/{arm}/{intake}"] for intake in ("correct", "incorrect")]
        row = [sum(c[key] for c in conditions) for key in ("complete", "capped", "unscored")]
        assert sum(row) == sum(c["planned"] for c in conditions) == 18
        rows.append(row)
assert sum(r[0] for r in rows) == summary["complete_campaigns"] == 51
assert sum(sum(r) for r in rows) == summary["planned_campaigns"] == 72
fig, ax = plt.subplots(figsize=(10, 4.8), layout="constrained")
left = [0] * len(rows)
for index, (label, color) in enumerate(zip(("Finished", "Stage limit", "Response missing"), ("#177c68", "#db9d2d", "#7d8795"))):
    values = [row[index] for row in rows]
    ax.barh(range(4), values, left=left, color=color, label=label, height=0.57)
    for y, (start, value) in enumerate(zip(left, values)):
        if value:
            ax.text(start + value / 2, y, str(value), ha="center", va="center", color="white" if index != 1 else "#222222", fontweight="bold")
    left = [start + value for start, value in zip(left, values)]
ax.set_yticks(range(4), ("July solo", "July live team", "October solo", "October live team"))
ax.invert_yaxis()
ax.set_xlim(0, 18)
ax.set_xticks(range(0, 19, 3))
ax.set_xlabel("Planned jobs (18 in each setup)")
ax.set_title("October finished fewer jobs in teams than alone", loc="left", pad=18, fontsize=13)
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=3, frameon=False)
ax.spines[["top", "right", "left"]].set_visible(False)
ax.tick_params(axis="y", length=0)
fig.savefig(HERE / "completion.png", dpi=180, metadata={"Software": "Matplotlib; committed V3 summary"})
plt.close(fig)
