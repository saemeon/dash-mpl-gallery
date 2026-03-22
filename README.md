[![PyPI](https://img.shields.io/pypi/v/dash-interact)](https://pypi.org/project/dash-interact/)
[![Python](https://img.shields.io/pypi/pyversions/dash-interact)](https://pypi.org/project/dash-interact/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Plotly](https://img.shields.io/badge/Plotly-3F4F75?logo=plotly&logoColor=white)](https://plotly.com/python/)
[![Dash](https://img.shields.io/badge/Dash-008DE4?logo=plotly&logoColor=white)](https://dash.plotly.com/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)

# dash-interact

Build interactive Plotly Dash apps from type-hinted Python functions — pyplot-style, no boilerplate.

```python
from dash_interact import page

page.H1("My App")

@page.interact
def sine_wave(amplitude: float = 1.0, frequency: float = 2.0, n_cycles: int = 3):
    import numpy as np, plotly.graph_objects as go
    x = np.linspace(0, n_cycles * 2 * np.pi, 600)
    return go.Figure(go.Scatter(x=x, y=amplitude * np.sin(frequency * x)))

page.run(debug=True)
```

## Installation

```bash
pip install dash-interact
```

## How it works

`@page.interact` inspects the function signature and generates a Dash form automatically:

- `float` / `int` → slider or number input
- `bool` → checkbox
- `Literal[...]` → dropdown
- `str` → text input
- `date` / `datetime` → date picker

The return value is rendered automatically — Plotly figures become `dcc.Graph`, DataFrames become a `DataTable`, strings become Markdown, and so on.

## Quickstart

### Implicit (pyplot-style)

```python
from dash_interact import page

page.H1("Dashboard")

@page.interact
def histogram(n_samples: int = 500, bins: int = 40):
    import numpy as np, plotly.graph_objects as go
    data = np.random.default_rng(42).normal(size=n_samples)
    return go.Figure(go.Histogram(x=data, nbinsx=bins))

page.run(debug=True)
```

### Explicit (embed into a larger layout)

```python
from dash import Dash, html
from dash_interact import Page

p = Page()
p.H1("Dashboard")

@p.interact
def histogram(n_samples: int = 500, bins: int = 40):
    ...

app = Dash(__name__)
app.layout = html.Div([navbar, p, footer])
app.run(debug=True)
```

### Field customization

```python
from dash_interact import page
from dash_fn_forms import Field

@page.interact(amplitude=(0.1, 3.0, 0.1))   # tuple → min/max/step
def sine_wave(
    amplitude: float = 1.0,
    frequency: float = 2.0,
    label: str = Field(label="Title", description="Chart title"),
):
    ...
```

### Custom renderers

```python
import pandas as pd
from dash import dash_table
from dash_fn_forms import register_renderer

register_renderer(
    pd.DataFrame,
    lambda df: dash_table.DataTable(data=df.to_dict("records")),
)

@page.interact
def get_data(rows: int = 10) -> pd.DataFrame:
    ...  # returned DataFrame is rendered as a DataTable automatically
```

## Packages

This repo contains two packages:

| Package | Install | Description |
|---------|---------|-------------|
| `dash-interact` | `pip install dash-interact` | pyplot-style page API (`page`, `interact`, `Page`) |
| `dash-fn-forms` | `pip install dash-fn-forms` | headless engine (`build_fn_panel`, `FnForm`, `Field`) |

Most users should install `dash-interact` — it includes the engine.

## Credits

| Feature | Inspiration |
|---------|-------------|
| `interact()` | [ipywidgets](https://ipywidgets.readthedocs.io/) — derive controls from a function signature |
| `page` singleton | [matplotlib.pyplot](https://matplotlib.org/stable/api/pyplot_summary.html) — implicit module-level state |
| top-to-bottom authoring | [Streamlit](https://streamlit.io/) / [Shiny Express](https://shiny.posit.co/py/docs/express.html) |
| visibility rules | [dash-pydantic-form](https://github.com/RenaudLN/dash-pydantic-form) |

## License

MIT
