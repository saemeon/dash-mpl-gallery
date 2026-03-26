[![PyPI](https://img.shields.io/pypi/v/gallery-viewer)](https://pypi.org/project/gallery-viewer/)
[![Python](https://img.shields.io/pypi/pyversions/gallery-viewer)](https://pypi.org/project/gallery-viewer/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Dash](https://img.shields.io/badge/Dash-008DE4?logo=plotly&logoColor=white)](https://dash.plotly.com/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![ty](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json)](https://github.com/astral-sh/ty)
[![prek](https://img.shields.io/badge/prek-checked-blue)](https://github.com/saemeon/prek)

# gallery-viewer

Configurable versioned script gallery dashboard for Dash — browse, edit, and execute data visualization scripts with date/version tracking.

## Installation

```bash
pip install gallery-viewer
```

## Usage

```python
from gallery_viewer import Gallery, FileSystemBackend

backend = FileSystemBackend(base_dir="./my_project")
gallery = Gallery(backend=backend, title="My Gallery")
gallery.run()
```

## Features

- Browse scripts by date and version
- Live code editor with section markers (LOAD / PLOT / SAVE)
- Preview plots before saving
- Data table viewer
- Pluggable storage backends (`FileSystemBackend` or custom)
- Optional export function for post-processing (e.g. corporate framing)

## File structure

```
my_project/
├── data/
│   └── data_20260101.csv
├── scripts/
│   ├── script_20260101_v1.py
│   └── script_20260101_v2.py
└── plots/
    └── plot_20260101_v1.png
```

## License

MIT
