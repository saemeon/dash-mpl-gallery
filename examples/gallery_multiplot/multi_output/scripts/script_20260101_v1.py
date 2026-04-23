# === CONFIGURATOR ===
title: str = "Regional Revenue"
highlight_region: str = "EMEA"
show_total: bool = True

# === CODE ===
import matplotlib
import pandas as pd

matplotlib.use("Agg")
from pathlib import Path

import matplotlib.pyplot as plt

BASE_DIR = Path(__file__).parent.parent
date = "20260101"

df = pd.read_csv(BASE_DIR / "data" / f"data_{date}.csv")
quarters = ["q1", "q2", "q3", "q4"]

# Output 1: bar chart by region
fig, ax = plt.subplots(figsize=(8, 5))
x = range(len(quarters))
width = 0.25
for i, (_, row) in enumerate(df.iterrows()):
    offset = (i - len(df) / 2 + 0.5) * width
    color = "#5b9bd5" if row["region"] == highlight_region else "#999"
    ax.bar([xi + offset for xi in x], [row[q] for q in quarters],
           width=width, label=row["region"], color=color, alpha=0.85)

ax.set_xticks(x)
ax.set_xticklabels([q.upper() for q in quarters])
ax.set_title(title)
ax.set_ylabel("CHF millions")
ax.legend()
ax.grid(axis="y", alpha=0.3)
plt.tight_layout()

# Output 2: summary table
summary = df.copy()
summary["total"] = summary[quarters].sum(axis=1)
summary["avg"] = summary[quarters].mean(axis=1).round(1)

# Output 3: totals chart (optional)
if show_total:
    fig2, ax2 = plt.subplots(figsize=(8, 3))
    colors = ["#5b9bd5" if r == highlight_region else "#999" for r in summary["region"]]
    ax2.barh(summary["region"], summary["total"], color=colors)
    ax2.set_xlabel("CHF millions (annual)")
    ax2.set_title("Annual Total by Region")
    ax2.grid(axis="x", alpha=0.3)
    plt.tight_layout()

# === SAVE ===
# The gallery injects: date, version, BASE_DIR, PLOT_OUTPUT_PATH
from pathlib import Path
Path(PLOT_OUTPUT_PATH).parent.mkdir(parents=True, exist_ok=True)
plt.figure(fig.number)
plt.savefig(PLOT_OUTPUT_PATH, dpi=150)
print(f"Saved {PLOT_OUTPUT_PATH}")
