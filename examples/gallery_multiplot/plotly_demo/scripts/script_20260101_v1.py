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
    mode="lines+markers",
    name="CPI",
    line=dict(color=color_cpi, width=2),
))

if show_core:
    fig.add_trace(go.Scatter(
        x=df["month"], y=df["core_cpi"],
        mode="lines+markers",
        name="Core CPI",
        line=dict(color="#e84133", width=2, dash="dash"),
    ))

fig.update_layout(
    title=title,
    yaxis_title="Index (base=100)",
    template="plotly_dark",
    height=450,
)

# === SAVE ===
# The gallery injects: date, version, BASE_DIR, PLOT_OUTPUT_PATH
# Plotly can also export static images if kaleido is installed
print(f"Plotly figure with {len(fig.data)} traces")
