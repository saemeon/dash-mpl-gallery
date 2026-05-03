"""Gallery page — branch view at ``/branch/<branch_path>``.

The branch path is URL-encoded so that nested branches like
``finance/sub`` survive Dash's single-segment ``path_template`` capture
(see PAGES_MIGRATION.md §2 for why we couldn't use ``<path:path>``).

Card rendering moves here in Step 3; for now this is a placeholder that
proves routing + URL decoding.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import unquote

import dash
from dash import html

if TYPE_CHECKING:
    from gallery_viewer.gallery import Gallery

_gallery: Gallery | None = None


def bind(gallery: Gallery) -> None:
    """Attach the host Gallery and register page-scoped callbacks."""
    global _gallery
    _gallery = gallery
    # No callbacks today — gallery work happens in _layout(branch_path=...).


def _layout(branch_path: str | None = None) -> html.Div:
    decoded = unquote(branch_path or "")
    return html.Div(
        f"gallery placeholder — branch: {decoded!r}",
        id="gv-gallery-placeholder",
    )


dash.register_page(__name__, path_template="/branch/<branch_path>", layout=_layout)
