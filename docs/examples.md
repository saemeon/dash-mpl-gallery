# Examples

## Matplotlib chart

The most common case -- a single matplotlib figure with configurable parameters.

```python
# === CONFIGURATOR ===
title: str = "CPI Inflation"
show_core: bool = True
smoothing: int = 1
color_cpi: str = "#7CA3C6"

# === CODE ===
import matplotlib
import pandas as pd

matplotlib.use("Agg")
from pathlib import Path
import matplotlib.pyplot as plt

BASE_DIR = Path(__file__).parent.parent
date = "20260101"
df = pd.read_csv(BASE_DIR / "data" / f"data_{date}.csv", parse_dates=["month"])

fig, ax = plt.subplots(figsize=(8, 5))
cpi = df["cpi"]
if smoothing > 1:
    cpi = cpi.rolling(smoothing, min_periods=1).mean()

ax.plot(df["month"], cpi, linewidth=2, label="CPI", color=color_cpi)
if show_core:
    ax.plot(df["month"], df["core_cpi"], linewidth=2, label="Core CPI",
            color="#e84133", linestyle="--")

ax.set_title(title)
ax.set_ylabel("Index (base=100)")
ax.legend()
ax.grid(alpha=0.3)
fig.autofmt_xdate()
plt.tight_layout()
```

## Plotly interactive chart

Same data, interactive output. Requires `plotly` installed.

```python
# === CONFIGURATOR ===
title: str = "CPI Inflation (Interactive)"
show_core: bool = True
color_cpi: str = "#7CA3C6"

# === CODE ===
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
date = "20260101"
df = pd.read_csv(BASE_DIR / "data" / f"data_{date}.csv", parse_dates=["month"])

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=df["month"], y=df["cpi"],
    mode="lines+markers", name="CPI",
    line=dict(color=color_cpi, width=2),
))
if show_core:
    fig.add_trace(go.Scatter(
        x=df["month"], y=df["core_cpi"],
        mode="lines+markers", name="Core CPI",
        line=dict(color="#e84133", width=2, dash="dash"),
    ))
fig.update_layout(title=title, yaxis_title="Index", template="plotly_dark")
```

The gallery auto-detects the Plotly figure and renders it as an interactive `dcc.Graph`.

## Multi-output script

A single script producing two charts and a summary table:

```python
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

# Output 1: bar chart
fig, ax = plt.subplots(figsize=(8, 5))
width = 0.25
for i, (_, row) in enumerate(df.iterrows()):
    offset = (i - len(df) / 2 + 0.5) * width
    color = "#5b9bd5" if row["region"] == highlight_region else "#999"
    ax.bar([xi + offset for xi in range(len(quarters))],
           [row[q] for q in quarters], width=width,
           label=row["region"], color=color)
ax.set_title(title)
ax.legend()
plt.tight_layout()

# Output 2: summary table (auto-captured as DataFrame)
summary = df.copy()
summary["total"] = summary[quarters].sum(axis=1)
summary["avg"] = summary[quarters].mean(axis=1).round(1)

# Output 3: totals chart (optional)
if show_total:
    fig2, ax2 = plt.subplots(figsize=(8, 3))
    colors = ["#5b9bd5" if r == highlight_region else "#999"
              for r in summary["region"]]
    ax2.barh(summary["region"], summary["total"], color=colors)
    ax2.set_title("Annual Total by Region")
    plt.tight_layout()
```

The preview panel shows: bar chart, summary table, and totals chart -- all from one script.

## Multi-plot gallery config

```json
{
  "title": "My Gallery",
  "plots": {
    "revenue": {"path": "./revenue", "description": "Quarterly revenue"},
    "inflation": {"path": "./inflation", "description": "CPI tracking"},
    "plotly_demo": {"path": "./plotly_demo", "description": "Interactive chart"}
  }
}
```

```python
from gallery_viewer import Gallery

gallery = Gallery.from_config("gallery.json")
gallery.run()
```
