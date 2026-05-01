"""Multi-plot gallery demo with JSON config.

Demonstrates:
  - Multiple named plots (revenue_chart, inflation)
  - gallery.json config file
  - "Add Plot" button for creating new plots from the dashboard
  - Type-hinted parameters in scripts (convention + decorator)

Usage:
    uv run python examples/gallery_multiplot_demo.py
"""

import os
from pathlib import Path

from gallery_viewer import Gallery

DEMO_DIR = Path(__file__).parent / "gallery_multiplot"
CONFIG = DEMO_DIR / "gallery.json"

os.chdir(DEMO_DIR)

gallery = Gallery.from_config(CONFIG)

if __name__ == "__main__":
    print(f"Gallery dir: {DEMO_DIR}")
    print(f"Config: {CONFIG}")
    print(f"Plots: {list(gallery.backends.keys())}")
    gallery.run(port=8050)
