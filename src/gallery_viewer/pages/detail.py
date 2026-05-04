"""Detail page — script editor + preview view at ``/``.

Reads URL query params ``?id=&group=&version=`` for the selected leaf
and version. The editor + preview cluster lives in
``Gallery._build_detail_layout`` so that the host class still owns the
component tree (and the callbacks that target it). This page module is a
thin mount-point that calls into it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import dash
import dash_bootstrap_components as dbc
from dash import html

if TYPE_CHECKING:
    from gallery_viewer.gallery import Gallery

_gallery: Gallery | None = None


def bind(gallery: Gallery) -> None:
    """Attach the host Gallery and register page-scoped callbacks."""
    global _gallery
    _gallery = gallery
    # Detail callbacks remain on the Gallery class for now; they fire via
    # @dash.callback regardless of where the layout is mounted.


def _layout(**_url_kwargs: object) -> html.Div:
    if _gallery is None:
        return html.Div("detail page used before bind()", style={"color": "#888"})
    return html.Div(
        dbc.Row(_gallery._build_detail_layout()),
        id="gv-detail-page",
    )


dash.register_page(__name__, path="/", layout=_layout)
