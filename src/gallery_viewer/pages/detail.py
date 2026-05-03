"""Detail page — script editor + preview view at ``/``.

Reads URL query params ``?id=&group=&version=`` for the selected leaf
and version. The full editor + preview cluster moves here in Step 4 of
PAGES_MIGRATION.md; for now this is a placeholder that proves routing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import dash
from dash import html

if TYPE_CHECKING:
    from gallery_viewer.gallery import Gallery

_gallery: Gallery | None = None


def bind(gallery: Gallery) -> None:
    """Attach the host Gallery and register page-scoped callbacks."""
    global _gallery
    _gallery = gallery
    # Callbacks land here in Step 4.


def _layout(**_url_kwargs: object) -> html.Div:
    return html.Div("detail page placeholder", id="gv-detail-placeholder")


dash.register_page(__name__, path="/", layout=_layout)
