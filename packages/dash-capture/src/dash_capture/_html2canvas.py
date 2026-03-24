"""Auto-include vendored html2canvas.min.js.

When ``capture_element`` uses html2canvas_strategy, the JS library is
automatically served via a Dash ``html.Script`` tag.  No CDN needed.
"""

from __future__ import annotations

from pathlib import Path

from dash import html

_ASSETS_DIR = Path(__file__).parent / "assets"
_LOADED = False


def html2canvas_script() -> html.Script:
    """Return a ``html.Script`` tag with the vendored html2canvas code.

    The script is loaded inline to avoid needing an external CDN.
    Call this once in your app layout::

        app.layout = html.Div([
            html2canvas_script(),
            ...
        ])

    Or use ``capture_element()`` which includes it automatically.
    """
    js_path = _ASSETS_DIR / "html2canvas.min.js"
    if not js_path.exists():
        raise FileNotFoundError(
            f"html2canvas.min.js not found at {js_path}. "
            "The vendored file may be missing from the package installation."
        )
    return html.Script(js_path.read_text())


def ensure_html2canvas(children: list) -> list:
    """Prepend html2canvas script to children list if not already present."""
    global _LOADED
    if not _LOADED:
        _LOADED = True
        return [html2canvas_script(), *children]
    return children
