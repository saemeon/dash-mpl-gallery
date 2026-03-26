"""gallery-viewer demo — generic gallery with filesystem backend.

Usage:
    # First generate demo data (uses the old demo_setup):
    cd ../corpframe-gallery && python demo_setup.py && cd ../dash-mpl-gallery

    # Then run:
    uv run python examples/gallery_demo.py
"""

from pathlib import Path
from gallery_viewer import Gallery, FileSystemBackend

DEMO_DIR = Path(__file__).resolve().parent.parent

gallery = Gallery(
    backend=FileSystemBackend(DEMO_DIR),
    title="Gallery Demo",
)

if __name__ == "__main__":
    print(f"Gallery base dir: {DEMO_DIR}")
    gallery.run(debug=False)
