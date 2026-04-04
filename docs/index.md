# gallery-viewer

A configurable Dash dashboard for browsing, editing, and executing versioned data visualization scripts. Designed for teams that iterate on report charts.

## Installation

```bash
pip install gallery-viewer
```

For interactive Plotly rendering:

```bash
pip install gallery-viewer plotly
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

See [Architecture](architecture.md) for how scripts, backends, and the dashboard fit together.

See [Examples](examples.md) for complete working scripts.
