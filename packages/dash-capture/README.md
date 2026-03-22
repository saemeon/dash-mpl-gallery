[![PyPI](https://img.shields.io/pypi/v/dash-capture)](https://pypi.org/project/dash-capture/)
[![Python](https://img.shields.io/pypi/pyversions/dash-capture)](https://pypi.org/project/dash-capture/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Plotly](https://img.shields.io/badge/Plotly-3F4F75?logo=plotly&logoColor=white)](https://plotly.com/python/)
[![Dash](https://img.shields.io/badge/Dash-008DE4?logo=plotly&logoColor=white)](https://dash.plotly.com/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![ty](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json)](https://github.com/astral-sh/ty)
[![prek](https://img.shields.io/badge/prek-checked-blue)](https://github.com/saemeon/prek)

# dash-capture

Browser capture & custom renderer pipeline for Plotly Dash components.

## Installation

```bash
pip install dash-capture
```

## Components

| Component | Description |
|-----------|-------------|
| `graph_exporter` | Capture wizard for `dcc.Graph` — modal with auto-generated fields, live preview, and PNG download |
| `build_wizard` | Generic modal dialog |
| `build_dropdown` | Generic anchored dropdown with click-outside-to-close |
| `FromPlotly` | `FieldHook` that pre-fills a field from the live Plotly figure |
| `FieldHook` | Base class for runtime field defaults derived from Dash component state |

**Supported field types:** `str`, `int`, `float`, `bool`, `date`, `datetime`, `Literal[...]`, `list[T]`, `tuple[T, ...]`, `T | None`

## License

MIT
