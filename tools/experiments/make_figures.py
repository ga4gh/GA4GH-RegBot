"""
Paper figures from the experiment result files (static PDF + PNG for LaTeX).

    python tools/experiments/make_figures.py --results ~/Desktop/GSoC/05_Paper/results --out figures/

Figure 1  aspect collapse: provision recall of a single whole-text query vs per-aspect
          retrieval as the number of aspects grows, for two encoders and two budgets.
Figure 2  encoder × fusion interaction on the 41-query gold set.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List, Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Validated categorical slots (dataviz reference palette, light surface): blue, orange.
BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, MUTED, GRID = "#0b0b0b", "#898781", "#e1e0d9"

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.size": 9,
        "axes.edgecolor": "#c3c2b7",
        "axes.labelcolor": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
        "pdf.fonttype": 42,
    }
)


def _load(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def figure_collapse(results_dir: str, out: str) -> None:
    runs = {
        "MiniLM-L6 hybrid": _load(os.path.join(results_dir, "pilot.json"))["results"],
        "Qwen3-Emb hybrid": _load(os.path.join(results_dir, "pilot_qwen3.json"))["results"],
    }
    ms = [1, 2, 3, 4, 6]
    fig, axes = plt.subplots(1, 2, figsize=(6.4, 2.6), sharey=True)
    for ax, budget in zip(axes, (8, 24)):
        for (enc, res), style in zip(runs.items(), ("-", "--")):
            single = [res[f"m={m},budget={budget}"]["single"]["provision_recall"] for m in ms]
            rr = [res[f"m={m},budget={budget}"]["rr"]["provision_recall"] for m in ms]
            ax.plot(
                ms,
                single,
                style,
                color=ORANGE,
                lw=2,
                marker="o",
                ms=4,
                label=f"whole-text query · {enc}",
            )
            ax.plot(
                ms,
                rr,
                style,
                color=BLUE,
                lw=2,
                marker="o",
                ms=4,
                label=f"per-aspect retrieval · {enc}",
            )
        ax.set_title(f"budget = {budget} slots", loc="left", fontsize=9, color=INK)
        ax.set_xlabel("aspects in the query (m)")
        ax.set_xticks(ms)
        ax.set_ylim(0, 1)
        ax.grid(axis="y", color=GRID, lw=0.6)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("provision recall (union of m gold sets)")
    # Direct labels on the right panel, where the two groups are furthest apart.
    res = runs["MiniLM-L6 hybrid"]
    axes[1].annotate(
        "per-aspect",
        (6, res["m=6,budget=24"]["rr"]["provision_recall"]),
        xytext=(4, 4),
        textcoords="offset points",
        color=BLUE,
        fontsize=8,
    )
    axes[1].annotate(
        "whole text",
        (6, res["m=6,budget=24"]["single"]["provision_recall"]),
        xytext=(4, -10),
        textcoords="offset points",
        color=ORANGE,
        fontsize=8,
    )
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles, labels, loc="lower center", ncol=2, fontsize=7.5, bbox_to_anchor=(0.5, -0.08)
    )
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(out, f"fig_collapse.{ext}"), dpi=300, bbox_inches="tight")
    plt.close(fig)


def figure_fusion(results_dir: str, out: str) -> None:
    models = _load(os.path.join(results_dir, "models.json"))["summary"]
    core = _load(os.path.join(results_dir, "core.json"))["summary"]
    rows: List[tuple[str, float, float, float]] = [
        (
            "MiniLM-L6",
            core["baseline"]["provision_recall@8"]["mean"],
            core["fusion_sum"]["provision_recall@8"]["mean"],
            core["dense_only"]["provision_recall@8"]["mean"],
        ),
        (
            "bge-m3",
            models["bge_m3"]["provision_recall@8"]["mean"],
            models["bge_m3_sum"]["provision_recall@8"]["mean"],
            models["bge_m3_dense_only"]["provision_recall@8"]["mean"],
        ),
        (
            "Qwen3-Emb-0.6B",
            models["qwen3_0.6b"]["provision_recall@8"]["mean"],
            models["qwen3_sum"]["provision_recall@8"]["mean"],
            models["qwen3_dense_only"]["provision_recall@8"]["mean"],
        ),
    ]
    # A dot plot rather than bars: the interesting range is 0.77-0.91, and bars cut off
    # at 0.7 would exaggerate it. Marker shape carries identity alongside colour.
    fig, ax = plt.subplots(figsize=(4.4, 2.5))
    x = range(len(rows))
    series = (
        ("hybrid, max fusion", BLUE, "o"),
        ("hybrid, sum fusion", ORANGE, "s"),
        ("dense only", "#898781", "^"),
    )
    for i, (label, color, marker) in enumerate(series):
        vals = [r[i + 1] for r in rows]
        xs = [xi + (i - 1) * 0.22 for xi in x]
        ax.scatter(
            xs,
            vals,
            color=color,
            marker=marker,
            s=46,
            zorder=3,
            label=label,
            edgecolor="white",
            linewidth=0.8,
        )
        for xi, v in zip(xs, vals):
            ax.text(xi, v + 0.012, f"{v:.3f}", ha="center", va="bottom", fontsize=6.5, color=INK)
    for xi in x:
        ax.axvline(xi, color=GRID, lw=0.6, zorder=1)
    ax.set_xticks(list(x))
    ax.set_xticklabels([r[0] for r in rows])
    ax.set_xlim(-0.6, len(rows) - 0.4)
    ax.set_ylim(0.74, 0.95)
    ax.set_ylabel("provision recall@8")
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.legend(fontsize=7, loc="lower center", bbox_to_anchor=(0.5, -0.42), ncol=3)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(out, f"fig_fusion.{ext}"), dpi=300, bbox_inches="tight")
    plt.close(fig)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    figure_collapse(args.results, args.out)
    figure_fusion(args.results, args.out)
    print(f"figures written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
