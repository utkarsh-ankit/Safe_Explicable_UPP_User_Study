"""
Redraw every participant's route on the map they saw.

Reads the study database (read-only) and writes PNGs:

  out/participants/<condition>_<domain>_<prolific_id>.png   one route each
  out/overlay_<domain>_<condition>.png                      all routes overlaid

By default only participants who completed the survey AND passed the
attention check are drawn. Use --all to include everyone with a trial.

Usage (needs matplotlib):
  python analysis/plot_routes.py data/study.sqlite3 --out route_plots
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from study.domains import get_domain_config  # noqa: E402

COLORS = {
    "floor": "#ffffff",
    "wall": "#8a97a3",
    "room": "#eaf3ea",
    "busy": "#ffd296",
    "coffee": "#2a9d8f",
    "office": "#1a3d7c",
    "photo": "#2a9d8f",
    "low": "#f0a202",
    "high": "#c1121f",
    "route": "#1d3557",
    "start": "#0a7d2c",
}


def load_trials_csv(csv_path: str, include_all: bool):
    import csv
    out = []
    with open(csv_path, newline="") as f:
        for r in csv.DictReader(f):
            if not r.get("trajectory_json"):
                continue
            if not include_all and not (r["completed_at"] and r["sanity_passed"] == "1"):
                continue
            out.append({"pid": r["participant_code"], "condition": r["assigned_condition"],
                        "domain": r["domain_name"],
                        "path": [tuple(p) for p in json.loads(r["trajectory_json"])]})
    return out


def load_trials(db_path: str, include_all: bool):
    if db_path.endswith(".csv"):
        return load_trials_csv(db_path, include_all)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT p.participant_code, p.condition_name, p.completed_at,
               COALESCE((SELECT MAX(sc.passed) FROM sanity_checks sc
                         WHERE sc.participant_id = p.id), 0) AS passed,
               t.domain_name, t.trajectory_json
        FROM participants p
        JOIN trials t ON t.participant_id = p.id
        ORDER BY p.id, t.task_index
        """
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        if not include_all and not (r["completed_at"] and r["passed"] == 1):
            continue
        out.append(
            {
                "pid": r["participant_code"],
                "condition": r["condition_name"],
                "domain": r["domain_name"],
                "path": [tuple(p) for p in json.loads(r["trajectory_json"])],
            }
        )
    return out


def draw_map(ax, cfg):
    n = cfg["grid_size"]
    blocked = {tuple(c) for c in cfg.get("blocked_cells", [])}
    room = {tuple(c) for cells in cfg.get("room_cells", {}).values() for c in cells}
    busy = {tuple(c) for c in cfg.get("visible_busy", [])}
    for r in range(n):
        for c in range(n):
            if (r, c) in blocked:
                fc = COLORS["wall"]
            elif (r, c) in busy:
                fc = COLORS["busy"]
            elif (r, c) in room:
                fc = COLORS["room"]
            else:
                fc = COLORS["floor"]
            ax.add_patch(Rectangle((c - 0.5, r - 0.5), 1, 1, facecolor=fc,
                                   edgecolor="#d9dee3", lw=0.5, zorder=0))

    for key, level in cfg.get("visible_debris", {}).items():
        r, c = map(int, key.split(","))
        ax.add_patch(Rectangle((c - 0.5, r - 0.5), 1, 1, facecolor=COLORS[level],
                               edgecolor="black", lw=1, zorder=1))

    for r1, c1, r2, c2 in cfg.get("blocked_edges", []):
        if r1 == r2:  # vertical wall between columns
            x = max(c1, c2) - 0.5
            ax.plot([x, x], [r1 - 0.5, r1 + 0.5], color="black", lw=3, zorder=2)
        else:  # horizontal wall between rows
            y = max(r1, r2) - 0.5
            ax.plot([c1 - 0.5, c1 + 0.5], [y, y], color="black", lw=3, zorder=2)
    ax.add_patch(Rectangle((-0.5, -0.5), n, n, fill=False, edgecolor="black", lw=2, zorder=2))

    for name, (r, c) in cfg.get("photo_targets", {}).items():
        ax.add_patch(plt.Circle((c, r), 0.3, color=COLORS["photo"], zorder=3))
        ax.text(c, r, name, ha="center", va="center", color="white", fontsize=8,
                fontweight="bold", zorder=4)
    for key, label in cfg.get("labels", {}).items():
        r, c = map(int, key.split(","))
        ax.text(c, r, label, ha="center", va="center", fontsize=12, fontweight="bold",
                color=COLORS["start"] if label == "S" else "#333333", zorder=4)
    sr, sc = cfg["start"]
    ax.add_patch(plt.Circle((sc, sr), 0.38, fill=False, edgecolor=COLORS["start"], lw=2, zorder=4))

    ax.set_xlim(-0.5, n - 0.5)
    ax.set_ylim(n - 0.5, -0.5)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])


def draw_route(ax, path, alpha=1.0, lw=2.0):
    m = len(path)
    for i in range(m - 1):
        (r0, c0), (r1, c1) = path[i], path[i + 1]
        ax.annotate("", xy=(c1, r1), xytext=(c0, r0),
                    arrowprops=dict(arrowstyle="-|>", color=COLORS["route"], lw=lw,
                                    alpha=alpha, shrinkA=4, shrinkB=4),
                    zorder=5)


def draw_overlay_colored(ax, paths, labels=None):
    """One colour per participant, each route nudged slightly so overlaps stay visible."""
    import numpy as np

    cmap = plt.get_cmap("tab20")
    k = max(1, len(paths))
    for i, path in enumerate(paths):
        color = cmap(i % 20)
        off = (i - (k - 1) / 2) * min(0.035, 0.6 / k)
        xs = np.array([c for _, c in path], dtype=float) + off
        ys = np.array([r for r, _ in path], dtype=float) + off
        ax.plot(xs, ys, color=color, lw=1.8, alpha=0.9, solid_capstyle="round",
                label=labels[i] if labels else None, zorder=5)
        ax.plot(xs[-1], ys[-1], marker="o", color=color, ms=4, zorder=6)
    if labels:
        ax.legend(fontsize=5.5, loc="upper left", bbox_to_anchor=(1.01, 1.0),
                  frameon=False, ncol=1)


def draw_overlay(ax, paths):
    edges = Counter()
    for path in paths:
        for a, b in zip(path, path[1:]):
            edges[(a, b)] += 1
    if not edges:
        return
    top = max(edges.values())
    for ((r0, c0), (r1, c1)), k in edges.items():
        ax.plot([c0, c1], [r0, r1], color=COLORS["route"], lw=1 + 6 * k / top,
                alpha=0.25 + 0.6 * k / top, solid_capstyle="round", zorder=5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db", help="path to study.sqlite3 or the exported CSV")
    ap.add_argument("--out", default="route_plots")
    ap.add_argument("--all", action="store_true",
                    help="include participants who failed the check or did not finish")
    args = ap.parse_args()

    trials = load_trials(args.db, args.all)
    os.makedirs(os.path.join(args.out, "participants"), exist_ok=True)

    groups: dict[tuple[str, str], list] = {}
    for t in trials:
        cfg = get_domain_config(t["domain"], t["condition"])
        fig, ax = plt.subplots(figsize=(5, 5))
        draw_map(ax, cfg)
        draw_route(ax, t["path"])
        ax.set_title(f"{cfg['title']} — {cfg['condition_label']}\n{t['pid']}  ({len(t['path']) - 1} moves)",
                     fontsize=9)
        fig.tight_layout()
        fig.savefig(os.path.join(args.out, "participants",
                                 f"{t['condition']}_{t['domain']}_{t['pid']}.png"), dpi=130)
        plt.close(fig)
        groups.setdefault((t["domain"], t["condition"]), []).append((t["pid"], t["path"]))

    for (domain, condition), items in sorted(groups.items()):
        pids = [pid for pid, _ in items]
        paths = [p for _, p in items]
        cfg = get_domain_config(domain, condition)
        fig, ax = plt.subplots(figsize=(8, 6))
        draw_map(ax, cfg)
        draw_overlay_colored(ax, paths, [p[:8] for p in pids])
        ax.set_title(f"{cfg['title']} — {cfg['condition_label']}  (n = {len(paths)})\n"
                     "one colour per participant; dot = end of route", fontsize=10)
        fig.tight_layout()
        fig.savefig(os.path.join(args.out, f"overlay_colored_{domain}_{condition}.png"), dpi=170)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(6, 6))
        draw_map(ax, cfg)
        draw_overlay(ax, paths)
        ax.set_title(f"{cfg['title']} — {cfg['condition_label']}  (n = {len(paths)})\n"
                     "thicker / darker = more participants took that step", fontsize=10)
        fig.tight_layout()
        fig.savefig(os.path.join(args.out, f"overlay_{domain}_{condition}.png"), dpi=150)
        plt.close(fig)

    print(f"{len(trials)} routes drawn → {os.path.abspath(args.out)}")
    for (domain, condition), paths in sorted(groups.items()):
        print(f"  {domain:13s} {condition:8s} n={len(paths)}")


if __name__ == "__main__":
    main()
