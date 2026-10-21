"""Figures for the peer-transmission review. Reads the CSV/JSONL outputs, writes PNGs.

Usage: python3 figures.py notes.jsonl out/ fig/   (needs matplotlib, so no -I)
"""
import csv, json, os, sys
from collections import Counter
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

notes, out, fig = sys.argv[1], sys.argv[2], sys.argv[3]
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE, AQUA, YELLOW, MAGENTA = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2,
                     "ytick.color": INK, "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF})


def clean(ax):
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.xaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def hstack(ax, labels, series, colors, names, short=None):
    """Stacked bars. Segments too narrow for an in-bar number are named in the end label instead."""
    short = short or names
    totals = [sum(col) for col in zip(*series)]
    wide = max(totals) * 0.05
    left, extra = [0] * len(labels), [[] for _ in labels]
    for vals, c, n, s in zip(series, colors, names, short):
        ax.barh(labels, vals, left=left, color=c, height=0.6, edgecolor=SURF, linewidth=2, label=n)
        for i, v in enumerate(vals):
            if v >= wide:
                ax.text(left[i] + v / 2, i, str(v), ha="center", va="center", color="white", fontsize=9, fontweight="bold")
            elif v:
                extra[i].append(f"{v} {s}")
        left = [l + v for l, v in zip(left, vals)]
    for i, t in enumerate(totals):
        parts = sum(1 for vals in series if vals[i])
        end = extra[i][0] if parts == 1 and extra[i] else f"{t}" + (f"  ({', '.join(extra[i])})" if extra[i] else "")
        ax.text(t + max(totals) * 0.012, i, end, va="center", color=INK2, fontsize=9)
    ax.set_xlim(0, max(totals) * 1.22)
    ax.invert_yaxis()


def top_legend(ax, ncol, pad):
    """Legend in a row between the title and the plot, so it never sits on a bar or the axis label."""
    ax.legend(frameon=False, ncol=ncol, fontsize=8.5, loc="lower left", bbox_to_anchor=(0, 1.0),
              borderaxespad=0.3, handlelength=1.2, columnspacing=1.4)
    ax.title.set_position((0, 1.0)); ax.set_title(ax.get_title(loc="left"), loc="left", pad=pad, color=INK, fontsize=12)


# 1. Crossings by family and type
W = ("resource_write", "cache_put", "service_request", "project_write")
fam = lambda s: s.split("-")[0] if s.startswith(("hf", "sol", "wayfinding")) else s
rows = [json.loads(l) for l in open(notes)]
cr = [r for r in rows if r["kind"] == "crossing"]
c = Counter((fam(r["study"]), "w" if str(r.get("method")).upper() in ("PUT", "POST", "PATCH") or r["op"] in W else "r") for r in cr)
order = ["hf", "sol", "wayfinding", "payment-draft-repair-v1", "payment-route-transfer-v1", "payables-v1", "settlement-close-v1"]
nice = ["hf-*", "sol-*", "wayfinding-*", "payment-draft-repair", "payment-route-transfer", "payables", "settlement-close"]
f, ax = plt.subplots(figsize=(8, 3.8))
hstack(ax, nice, [[c[(o, "r")] for o in order], [c[(o, "w")] for o in order]], [BLUE, ORANGE], ["read", "write"],
       ["read", "write"])
clean(ax)
ax.set_xlabel("crossings: operations the world marked not permitted that still succeeded")
ax.set_title(f"Two out of three of the {len(cr)} crossings are reads", loc="left")
top_legend(ax, 2, 22)
f.savefig(os.path.join(fig, "1-crossings-by-family.png"), dpi=160, bbox_inches="tight", pad_inches=0.15); plt.close(f)

# 2. What write-crossers told peers afterwards
ad = list(csv.DictReader(open(os.path.join(out, "admission_coding.csv"))))
group = {"result_only": "Result only", "partial": "Partial procedure", "pointer": "Path or procedure, no exception label",
         "passive_proc": "Path or procedure, no exception label", "first_person": "Path or procedure, no exception label",
         "pointer+passive_proc": "Path or procedure, no exception label", "exception": "Flags exception for owner", "kept_unverified": "Edited record but kept it unverified"}
cats = ["Result only", "Partial procedure", "Path or procedure, no exception label", "Flags exception for owner", "Edited record but kept it unverified"]
g = Counter((r["model"], group[r["code"]]) for r in ad)
f, ax = plt.subplots(figsize=(8, 2.3))
hstack(ax, ["DeepSeek V4 Pro", "Sol"], [[g[("deepseek", k)], g[("sol", k)]] for k in cats],
       [BLUE, AQUA, YELLOW, ORANGE, MAGENTA], cats)
clean(ax)
ax.set_xlabel("notes a worker wrote for peers after overriding a matching record (payment studies)")
ax.set_title("DeepSeek does not label its overrides, Sol almost always does", loc="left")
top_legend(ax, 3, 36)
f.savefig(os.path.join(fig, "2-admission-by-model.png"), dpi=160, bbox_inches="tight", pad_inches=0.15); plt.close(f)

# 3. Channel in payment-route-transfer: what later workers saw before their own override
ch = [r for r in csv.DictReader(open(os.path.join(out, "channel.csv"))) if "route-transfer" in r["run"] and r["override"]]
f, ax = plt.subplots(figsize=(8.8, 3.3))
ax.axis("off")
ax.set_xlim(0, 12.9); ax.set_ylim(0, 5.6)


def box(x, y, w, h, text, color):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.15", fc=SURF, ec=color, lw=2))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=8.5, color=INK, linespacing=1.4)


def arrow(x1, x2, y, color):
    ax.annotate("", xy=(x2, y), xytext=(x1, y), arrowprops=dict(arrowstyle="-|>,head_length=0.7,head_width=0.4", color=color, lw=2.4, mutation_scale=14,
                                                        shrinkA=0, shrinkB=0))


COLS = ((1.6, "earlier workers"), (5.55, "what later workers could read"), (9.5, "what later workers did"))
for x, head in COLS:
    ax.text(x + 1.6, 5.35, head, ha="center", va="center", fontsize=9, color=INK2)
for y, model, colr in ((2.95, "deepseek", BLUE), (0.25, "sol", ORANGE)):
    rs = [r for r in ch if model in r["run"]]
    ok = sum(int(r["saw_activity_ok"]) for r in rs); fail = sum(int(r["saw_activity_fail"]) for r in rs)
    readers = sum(1 for r in rs if int(r["saw_activity_ok"]))
    notes_seen = sum(int(r["saw_note"]) + int(r["saw_record"]) for r in rs)
    ax.text(0, y + 1.0, "DeepSeek" if model == "deepseek" else "Sol", va="center", fontsize=10, fontweight="bold", color=colr)
    box(1.6, y, 3.2, 2.0, "override matching.json\nwith a PUT", colr)
    arrow(4.95, 5.4, y + 1.0, colr)
    box(5.55, y, 3.2, 2.0, f"activity feed shows\nthe full request body\n\n{ok} successful, {fail} failed seen", colr)
    arrow(8.9, 9.35, y + 1.0, colr)
    res = f"{readers} saw a successful body\nand reused it on 6 invoices" if readers else "nobody saw a successful\nbody, no reuse"
    box(9.5, y, 3.2, 2.0, res + f"\n\nopened the changed record\nor a peer note: {notes_seen}", colr)
ax.set_title("route-transfer: the override travelled through the activity feed", loc="left", color=INK, fontsize=12)
f.savefig(os.path.join(fig, "3-route-transfer-channel.png"), dpi=160, bbox_inches="tight", pad_inches=0.15); plt.close(f)

# 4. Read-before-write funnel
fu = list(csv.DictReader(open(os.path.join(out, "funnel.csv"))))
pay = lambda x: "payment family" if x.startswith(("pay", "settle")) else x
fc = Counter((pay(r["family"]), r["pattern"]) for r in fu)
fams = ["hf", "sol", "wayfinding", "payment family"]
pats = ["read_only", "read_then_write", "write_then_read", "write_only"]
f, ax = plt.subplots(figsize=(8, 2.9))
hstack(ax, ["hf-*", "sol-*", "wayfinding-*", "payment studies"], [[fc[(x, p)] for x in fams] for p in pats],
       [BLUE, AQUA, YELLOW, ORANGE], ["read only", "read, then wrote", "wrote, then read", "wrote only"])
clean(ax)
ax.set_xlabel("workers (per run) with at least one crossing")
ax.set_title(f"{len(fu)} workers crossed a control, and most only read", loc="left")
top_legend(ax, 4, 22)
f.savefig(os.path.join(fig, "4-read-write-funnel.png"), dpi=160, bbox_inches="tight", pad_inches=0.15); plt.close(f)
print("ok")
