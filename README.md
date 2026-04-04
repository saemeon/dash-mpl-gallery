[![PyPI](https://img.shields.io/pypi/v/gallery-viewer)](https://pypi.org/project/gallery-viewer/)
[![Python](https://img.shields.io/pypi/pyversions/gallery-viewer)](https://pypi.org/project/gallery-viewer/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Dash](https://img.shields.io/badge/Dash-008DE4?logo=plotly&logoColor=white)](https://dash.plotly.com/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![ty](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json)](https://github.com/astral-sh/ty)
[![prek](https://img.shields.io/badge/prek-checked-blue)](https://github.com/saemeon/prek)

# gallery-viewer

A configurable Dash dashboard for browsing, editing, and executing versioned data visualization scripts. Designed for teams that iterate on report charts — one person writes the script, reviewers tweak parameters and save new versions.

## Installation

```bash
pip install gallery-viewer
```

## Quick start

```python
from gallery_viewer import Gallery, FileSystemBackend

# Single plot
gallery = Gallery(backend=FileSystemBackend("./my_project"))
gallery.run()

# Multi-plot from config
gallery = Gallery.from_config("gallery.json")
gallery.run()
```

## How it works

Scripts are split into three sections:

```python
# === CONFIGURATOR ===
title: str = "Q4 Revenue"       # rendered as a text field
show_target: bool = True         # rendered as a checkbox
dpi: int = 150                   # rendered as a number input

# === CODE ===
import matplotlib.pyplot as plt
fig, ax = plt.subplots()
ax.plot(df["x"], df["y"])
ax.set_title(title)

# === SAVE ===
# Optional post-processing (gallery handles plot saving automatically)
```

- **CONFIGURATOR** — typed variable assignments auto-generate form fields. Reviewers change these without touching code.
- **CODE** — the main script. Produces matplotlib figures, Plotly figures, DataFrames, or any combination.
- **SAVE** — runs only on "Save Version". For optional post-processing (extra exports, prints).

## Multi-output support

The gallery auto-detects what your script produces:

| Output type | Detection | Rendering |
|------------|-----------|-----------|
| matplotlib figure | Any open `plt` figure | PNG image |
| Plotly figure | `plotly.graph_objects.Figure` in namespace | Interactive `dcc.Graph` |
| pandas DataFrame | Non-private DataFrame variables | Data table |

Multiple outputs render stacked in the preview panel. A script can produce two charts and a summary table — all from one CODE section.

## Features

- **Date/version tracking** — scripts organized as `script_{date}_v{version}.py`
- **Parameter form fields** — CONFIGURATOR section auto-generates UI controls
- **RUN preview** — execute without saving, form values injected at runtime
- **Save Version** — creates next version for the selected date, clean script on disk
- **Version diff labels** — one-line summary of what changed from the previous version
- **Read-only mode** — toggle to hide the code editor (reviewers see only form fields + plot)
- **Export .py** — download as standalone script with all variables hardcoded
- **Author metadata** — optional name saved as comment in the script
- **New Date button** — detect uncharted data dates, pre-populate from latest version
- **Multi-plot galleries** — sidebar navigation with search/filter, backed by `gallery.json`
- **Pluggable backends** — `FileSystemBackend` or subclass `StorageBackend` for custom storage

## File structure

```
my_project/
  data/
    data_20260101.csv
    data_20260325.csv
  scripts/
    script_20260101_v1.py
    script_20260101_v2.py    # reviewer fixed the title
    script_20260325_v1.py    # new data release
  plots/
    plot_20260101_v1.png
    plot_20260101_v2.png
    plot_20260325_v1.png
```

## Multi-plot config

```json
{
  "title": "My Gallery",
  "plots": {
    "revenue": {"path": "./revenue", "description": "Quarterly revenue"},
    "inflation": {"path": "./inflation", "description": "CPI tracking"}
  }
}
```

```python
gallery = Gallery.from_config("gallery.json")
gallery.run()
```

## License

MIT
